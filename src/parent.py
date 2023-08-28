"""
AWS Nitro Test

Parent server that forwards requests it receives from the bastion
to the Nitro enclave via vsock
"""
import asyncio
import base64
import json
import os

import pprint
import click
import cbor2
import uvicorn

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from common.helper import get_cid
from common.messages import send_request_to_enclave
from common.config import ENCLAVE_HOST, PARENT_HOST, PARENT_PORT

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
    return "Hello from Parent"

@app.post("/post/", summary="Forward message to Nitro enclave", response_model=str)
def forward(message: Message):
    """Decode message and forward to the Nitro enclave for processing

    Args:
        message (Message): Message received via API

    Returns:
        str: Response from the Nitro enclave
    """
    # Hack
    simulate = True if os.getenv('NITRO_SIMULATION') == 'True' else False

    print('Message received:')
    pprint.PrettyPrinter(indent=4).pprint(message)

    payload_cbor = base64.b64decode(str.encode(message.payload))
    payload = cbor2.loads(payload_cbor)

    if simulate:
        print(f'Connecting to {ENCLAVE_HOST}. Sending: {message.payload}')
        response_obj = send_request_to_enclave(action = payload['action'],
                                    parameter = payload['parameter'], host=ENCLAVE_HOST)
    else:
        # Get CID of enclave
        cid = get_cid()
        if cid == 0:
            error_msg = "Cannot find an enclave to connect to"
            print(error_msg)
            return error_msg

        print(f'Connecting to CID {cid}. Sending: {message.payload}')
        response_obj = send_request_to_enclave(action = payload['action'],
                                    parameter = payload['parameter'], cid=cid)
    print(response_obj)
    response_obj_cbor = cbor2.dumps(response_obj)
    response_b64 = base64.b64encode(response_obj_cbor)
    response = json.dumps({'payload': response_b64.decode()})
    return response


@click.command()
@click.option('--simulate', type=bool, default=False,
              help='If set to True, assume the server simulates a Nitro enclave. Default is False.')
def parent(simulate: bool):
    """Launch parent API server after updating global parameter.

    Args:
        simulate (bool): If True, tells the server to communicate with a simulated Nitro enclave.
    """
    # Hack to pass argument to routing function
    os.environ['NITRO_SIMULATION'] = 'True' if simulate else 'False'

    # Lunch server
    config = uvicorn.Config("parent:app", port=PARENT_PORT, host=PARENT_HOST, log_level="debug")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())

if __name__ == '__main__':
    parent()  # pylint: disable=no-value-for-parameter
