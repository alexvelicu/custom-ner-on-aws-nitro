"""
AWS Nitro Test

Simple HTTP forwarder to run on bastion instance. It forwards traffic to
the parent of the Nitro enclave.
"""
import asyncio
import pprint
import os

import click
import requests
import uvicorn

from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from common.config import PARENT_API_URL, DEFAULT_TIMEOUT, BASTION_HOST, BASTION_PORT

class Message(BaseModel):
    """Basic API message
    """
    payload: str

# Set up the FastAPI app and define the endpoints
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

@app.get("/")
async def root():
    """Default GET method
    """
    return "Hello from bastion"

@app.post("/post/", summary="Forward message to the next server", response_model=str)
def forward(message: Message) -> str:
    """Forward the message received to the 

    Args:
        message (Message): Basic API message with string payload.

    Returns:
        str: Response from the next server
    """
    # Hack
    api_url = os.getenv('API_URL')

    print('Message received:')
    pprint.PrettyPrinter(indent=4).pprint(message)

    try:
        print(f'Connecting to {api_url}. Sending: {message.dict()}')
        response = requests.post(api_url, json=message.dict(), timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        return JSONResponse(status_code=500, content={'reason': str(error)})

    print('Response received:')
    pprint.PrettyPrinter(indent=4).pprint(response)

    return response.json()


@click.command()
@click.option('--api', type=str, default=PARENT_API_URL,
              help='API URL of bastion server.')
def bastion(api: str):
    """Launch bastion API server after updating global parameter

    Args:
        api (str): API URL of next server (i.e., parent server)
    """
    # Hack to pass argument to routing function
    os.environ['API_URL'] = api

    # Launch server
    config = uvicorn.Config("bastion:app", port=BASTION_PORT, host=BASTION_HOST, log_level="debug")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


if __name__ == "__main__":
    bastion()  # pylint: disable=no-value-for-parameter
