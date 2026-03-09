from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.dependencies import get_db
from app.models.user import User
from app.core.security import verify_password, create_access_token, set_auth_cookie, clear_auth_cookie

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.post("/login")
async def login(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    username = str(form.get("username", "")).strip().lower()
    password = str(form.get("password", ""))

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Usuario o contraseña incorrectos"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token(user.id)
    response = RedirectResponse(url="/map", status_code=status.HTTP_302_FOUND)
    set_auth_cookie(response, token)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    clear_auth_cookie(response)
    return response
