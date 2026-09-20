import os

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_HOST", "test")
os.environ.setdefault("DB_NAME", "test")

print(f"\
      DBUSER = {os.getenv("DB_USER")}\n\
      DB_PASSWORD = {os.getenv("DB_PASSWORD")}\n\
      DB_HOST = {os.getenv("DB_HOST")}\n\
      DB_NAME = {os.getenv("DB_NAME")}\n\
      ")