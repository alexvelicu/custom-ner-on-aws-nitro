"""
AWS Nitro Test

Server application that provides the NER API.
"""
import asyncio


from enum import Enum
import json
from typing import List
import os

import cbor2
import base64
import urllib.request
import click
from common.messages import send_request_to_enclave
import uvicorn
from fastapi import FastAPI

from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from common.config import CLIENT_HOST, CLIENT_PORT, ENCLAVE_HOST, CONTENT_1, CONTENT_2, CONTENT_3
from common.helper import pprint, verify_enclave, get_cid
from common.messages import get_attestation, send_encrypted_message


class ModelName(str, Enum):
    """Enum of the available models. This allows the API to raise a more specific
    error if an invalid model is provided.
    """
    ner_french = r"socsec_ner_fr"  # pylint: disable=invalid-name
    ner_dutch = r"socsec_ner_nl"  # pylint: disable=invalid-name

DEFAULT_MODEL = ModelName.ner_dutch
MODEL_NAMES = [model.value for model in ModelName]

class RequestModel(BaseModel):
    """Schema for processing requests on enclave
    """
    payload: str

class Text(BaseModel):
    """Schema for a single text in a batch of texts to process
    """
    content: str

class InputModel(BaseModel):
    """Schema for the text to process
    """
    texts: List[Text]
    model: ModelName = DEFAULT_MODEL

class Entity(BaseModel):
    """Schema for a single entity
    """
    text: str
    label: str
    start: int
    end: int
    person_title: str
    company_legal_form: str

class ResponseModel(BaseModel):
    """Schema of the expected response for a batch of processed texts
    """
    class Batch(BaseModel):
        """Schema of the response for a single processed text
        """
        text: str
        entities: List[Entity] = []
        html: str
    result: List[Batch]


# Set up the FastAPI app and define the endpoints
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])


@app.get("/")
async def root():
    """Default GET method
    """
    return "Hello from Proxy"

@app.post("/process/", summary="Forward message to the enclave server")
def post_message(req: RequestModel) -> List[str]:
    """ Forward the message received to the enclave server."""
    print("Process request received")
    pprint(req.json(), 'query')
    
    decoded = base64.b64decode(req.payload)
    obj = cbor2.loads(decoded)
    pprint(obj.json(), 'request')

    api=''
    cid = get_cid()
    host = ''

    # Request attestation from the server running in the Nitro enclave
    res = send_request_to_enclave(action=obj.action, parameter=obj.payload,
                                       cid=cid, host=host, api=api)
    response_obj_cbor = cbor2.dumps(res)
    response_b64 = base64.b64encode(response_obj_cbor)
    response = json.dumps({'payload': response_b64.decode()})
    return response


@app.post("/processtexts/", summary="Process batches of text", response_model=ResponseModel)
def process_texts(query: InputModel):
    """Process a batch of texts and return the entities predicted by the
    given model. Each record in the data should have a key "text".
    """
    print("Process request received")
    pprint(query.json(),'query')

    enclave_public_key = base64.b64decode(str.encode(os.getenv('ENCLAVE_PUBLIC_KEY')))
    api_url = os.getenv('API_URL')
    simulate = True if os.getenv('NITRO_SIMULATION') == 'True' else False

    if api_url:
        host = ''
        cid = 0
    elif simulate:
        host = ENCLAVE_HOST
        cid = 0
    else:
        # Get CID of enclave
        cid = get_cid()
        host = ''
        if cid == 0:
            error_msg = "Cannot find an enclave to connect to"
            print(error_msg)
            return error_msg

    # Request server to process query content
    response = send_encrypted_message(public_key=enclave_public_key,
                                      action='process', parameter=query.json(),
                                      cid=cid, host=host, api=api_url)
    with open('result.html', 'w', encoding='utf-8') as file:
        file.write(json.loads(response)['result'][0]['html'])
    pprint(response, 'Response')
    return ResponseModel(**json.loads(response))


@click.command()
@click.option('--desc', type=str, default='',
              help='JSON file containing the description of the EIF file.')
@click.option('--test', type=bool, default=False,
              help='Test sending some basic message to the server.')
@click.option('--api', type=str, default='',
              help='API URL of bastion server. Not set by default and assume client '
              'is running on enclave parent.')
@click.option('--simulate', type=bool, default=False,
              help='If set to True, assume the server simulates a Nitro enclave. Default is False.')
def main(desc: str, test: bool, api: str, simulate: bool):
    """Main function of the client that checks the attestation of the server,
    establishes an encryption key with the server and sends an encrypted message
    to the server.

    Args:
        desc (str): Name of file containing the description of the enclave
        test (bool): Run some basic tests first
        simulate (bool): If True, tells the server to communicate with a simulated Nitro enclave. 
    """
    # Hack to pass argument to routing function
    os.environ['API_URL'] = api
    os.environ['NITRO_SIMULATION'] = 'True' if simulate else 'False'

    if desc:
        desc = os.path.join(os.path.dirname(os.path.abspath(__file__)), desc)

    host=''
    cid=0
    if api:
        host = ''
        cid = 0
    elif simulate:
        host = ENCLAVE_HOST
        cid = 0
    else:
        # Get CID of enclave
        cid = get_cid()
        host = ''
        if cid == 0:
            error_msg = "Cannot find an enclave to connect to"
            print(error_msg)
            return error_msg
    pprint(simulate, 'Enclave simulation')
    pprint(host, 'Enclave address')
    pprint(cid, 'Enclave CID')
    pprint(api, 'Enclave parent address')

    attestation_doc = get_attestation(cid=cid, host=host, api=api)
    print('Attestation doc: ')
    print(base64.b64encode(attestation_doc).decode())
    
    # Request attestation from the server running in the Nitro enclave
    enclave_public_key = verify_enclave(desc, attestation_doc)
    os.environ['ENCLAVE_PUBLIC_KEY'] = base64.b64encode(enclave_public_key).decode()

    if test:
        # Send an encrypted message to the server
        data='Test message'
        response = send_encrypted_message(public_key=enclave_public_key, action='message',
                                          parameter=data,
                                          cid=cid, host=host, api=api)
        pprint(response, 'response')

        # Request the list of models
        model_names = send_encrypted_message(public_key=enclave_public_key, action='models',
                                             cid=cid, host=host, api=api)
        pprint(model_names, 'Available models')

        # Request server to process test content
        texts = [{"content": CONTENT_1}, {"content": CONTENT_2}, { "content": CONTENT_3 }]
        data = json.dumps({"texts": texts, "model": model_names[0]})
        response = send_encrypted_message(public_key=enclave_public_key,
                                          action='process', parameter=data,
                                          cid=cid, host=host, api=api)
        with open('result.html', 'w', encoding='utf-8') as file:
            file.write(json.loads(response)['result'][0]['html'])
        pprint(json.loads(response), 'Response')

    # Get public IP address of EC2 instance
    try:
        IP = urllib.request.urlopen("http://169.254.169.254/latest/meta-data/public-ipv4", timeout=5).read().decode()
        print(f'Public IP address of EC2 instance: {IP}')
    except:
        print('Not running on an AWS EC2 instance.')


    # Launch server
    config = uvicorn.Config("client:app", port=CLIENT_PORT, host=CLIENT_HOST, log_level="debug")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
