from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler

from contextlib import asynccontextmanager

from starlette.exceptions import HTTPException as StarletteHTTPException

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from typing import Annotated
from schema import PostCreate, PostResponse, UserCreate, UserResponse, PostUpdate, UserUpdate
import models
from database import Base, engine, get_db




@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory='static'), name='static')
app.mount("/media", StaticFiles(directory="media"), name='media')

templates = Jinja2Templates(directory="templates")


# <--- Template Routes --->

@app.get("/", include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
async def home(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    res = await db.execute(select(models.Post).options(selectinload(models.Post.author)))
    posts = res.scalars().all()
    return templates.TemplateResponse(
        request,
        "home.html",
        {"posts": posts, "title": "Home"}
    )


@app.get("/posts/{post_id}", include_in_schema=False)
async def post_page(request: Request, post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    res = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id))
    post = res.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND("Post not found")
        )
    title = post.title[:50]
    return templates.TemplateResponse(
        request,
        "post.html",
        {"post": post, "title": title}
    )


@app.get("/users/{user_id}/posts", include_in_schema=False, name="user_posts")
async def user_posts_page(request: Request, user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    res = db.execute(select(models.User).where(models.User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail = "User not found"
        )

    res = await db.execute(
        select(models.Post)
        .option(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id))
    posts = res.scalars().all()

    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"posts": posts, "user": user, "title": f"{user.username}'s Posts"}
    )



# <----- Errors Handlers ----->

@app.exception_handler(StarletteHTTPException)
async def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

    message = exception.detail if exception.detail else "An error occurred. Please check your request and try again."

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exception)

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )

# <-------------------- API -------------------->


# <----- Manage User ----->

@app.post('/api/users', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.username == user.username))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Username already exists")

    result = await db.execute(select(models.User).where(models.User.email == user.email))
    existing_email = result.scalars().first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Email already exists")
    
    new_user = models.User(
        username = user.username,
        email = user.email,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    res = await db.execute(select(models.User).where(models.User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.get('/api/user/{user_id}/posts', response_model=list[PostResponse])
async def get_user_posts(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    res = await db.execute(select(models.User).where(models.User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail = "User not found"
        )
    
    res = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id))
    posts = res.scalars().all()

    return posts



@app.patch("/api/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user_update.username is not None and user_update.username != user.username:
        result = await db.execute(
            select(models.User).where(models.User.username == user_update.username),
        )
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )
        user.username = user_update.username

    if user_update.email is not None and user_update.email != user.email:
        result = await db.execute(
            select(models.User).where(models.User.email == user_update.email),
        )
        existing_email = result.scalars().first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        user.email = user_update.email

    if user_update.image_file is not None:
        user.image_file = user_update.image_file

    await db.commit()
    await db.refresh(user)
    return user


@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await db.delete(user)
    await db.commit()



# <----- Manage Post ----->

@app.get("/api/posts", response_model=list[PostResponse])
async def get_posts(db: Annotated[AsyncSession,  Depends(get_db)]):
    res = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author)))
    posts = res.scalars().all()
    return posts


@app.get('/api/posts/{post_id}', response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession,  Depends(get_db)]):
    res = await db.execute(select(models.Post)
    .options(selectinload(models.Post.author))
    .where(models.Post.id == post_id))
    post = res.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@app.put('/api/posts/{post_id}', response_model=PostResponse)
async def update_post_full(post_id: int, post_data: PostCreate ,db: Annotated[AsyncSession, Depends(get_db)]):
    res = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = res.scalar()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Post not found')
    if post_data.user_id != post.user_id:
        res = await db.execute(select(models.User).where(models.User.id == post_data.user_id))
        user = res.scalar()
        if not user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User ID not match')

    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    await db.commit()
    await db.refresh(post, attribute_names=["author"])

    return post


@app.patch('/api/posts/{post_id}', response_model=PostResponse)
async def update_post_partial(post_id: int, post_data: PostUpdate, db: Annotated[AsyncSession, Depends(get_db)]):
    res = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = res.scalar()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    
    update_data = post_data.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(post, field, val)
    
    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post


@app.delete('/api/posts/{post_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    res = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = res.scalar()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    await db.delete(post)
    await db.commit()   


@app.post('/api/posts', response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post: PostCreate, db: Annotated[AsyncSession,  Depends(get_db)]):
    res = await db.execute(select(models.User).where(models.User.id == post.user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail = "User not found"
        )

    new_post = models.Post(
        title = post.title,
        content = post.content,
        user_id = post.user_id,
    )

    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])

    return new_post

