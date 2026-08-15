from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def hello():
    return {"msg":"FastAPI 启动成功"}