from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
from database import get_db
from schema import PostCreate, PostResponse, PostUpdate

router = APIRouter()


@router.get("", response_model=list[PostResponse])
async def get_posts(db: Annotated[AsyncSession,  Depends(get_db)]):
    res = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .order_by(models.Post.date_posted.desc()))
    posts = res.scalars().all()
    return posts


@router.get('/{post_id}', response_model=PostResponse)
async def get_post(post_id: int, db: Annotated[AsyncSession,  Depends(get_db)]):
    res = await db.execute(select(models.Post)
    .options(selectinload(models.Post.author))
    .where(models.Post.id == post_id))
    post = res.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.put('/{post_id}', response_model=PostResponse)
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


@router.patch('/{post_id}', response_model=PostResponse)
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


@router.delete('/{post_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    res = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = res.scalar()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    await db.delete(post)
    await db.commit()   


@router.post('', response_model=PostResponse, status_code=status.HTTP_201_CREATED)
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

