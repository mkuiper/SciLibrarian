from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import DB, CurrentUser
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserOut, Token
from app.services.auth import hash_password, authenticate_user, create_access_token, get_user_by_username

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, db: DB):
    existing = await get_user_by_username(db, data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = User(
        username=data.username.strip().lower(),
        name=data.name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
async def login(data: UserLogin, db: DB):
    user = await authenticate_user(db, data.username.strip().lower(), data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser):
    return current_user
