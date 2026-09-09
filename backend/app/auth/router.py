from fastapi import APIRouter, HTTPException, status
from .schemas import UserSignup, UserLogin, Token
from .utils import get_password_hash, verify_password, create_access_token

router = APIRouter()

# In-memory database for users
# Key: email, Value: hashed_password
fake_users_db = {}

@router.post("/signup", response_model=Token)
def signup(user: UserSignup):
    if user.email in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    hashed_password = get_password_hash(user.password)
    fake_users_db[user.email] = hashed_password

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
def login(user: UserLogin):
    if user.email not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    hashed_password = fake_users_db[user.email]
    if not verify_password(user.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout():
    # Since we are using stateless JWTs stored in memory on the frontend,
    # logout is handled mostly by the frontend dropping the token.
    # We can just return a success message here.
    return {"message": "Successfully logged out"}
