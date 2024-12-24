from typing import Callable
from fastapi import FastAPI


def create_start_app_handler(app: FastAPI) -> Callable:
    async def start_app() -> None:
        print("Starting up application...")
        # Add any startup tasks here (e.g., database connections)

    return start_app


def create_stop_app_handler(app: FastAPI) -> Callable:
    async def stop_app() -> None:
        print("Shutting down application...")
        # Add any cleanup tasks here

    return stop_app 