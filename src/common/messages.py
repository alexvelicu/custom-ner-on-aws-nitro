"""
AWS Nitro Test

Utility function for exchanging messages ove vsock with AWS Nitro Enclave
"""
import base64
import json
import pprint
import socket

import requests
import cbor2

from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

from common.config import VSOCK_PORT, DEFAULT_TIMEOUT
from common.helper import pprint

def encrypt(public_key: bytes, plaintext: bytes) -> bytes:
    """Encrypt message using public key in attestation document

    Args:
        public_key (bytes): RSA public key
        plaintext (bytes): Data bytes to be encrypted

    Returns:
        str: Plaintext data bytes encrypted with the RSA public key
    """
    public_key = RSA.import_key(public_key)
    cipher = PKCS1_OAEP.new(public_key)
    ciphertext = cipher.encrypt(plaintext)

    return ciphertext

def send_encrypted_message(public_key: bytes, action: str='', parameter: any=None,
                           cid: int=0, host: str='', api: str='') -> any:
    """Send encrypted message to a URL. It generates a random symmetric encryption
    key that is encrypted with the provided public key (e.g., of the enclave).

    Args:
        action (str): Request type string recognised by the server
        parameter (any): Data object to be sent
        public_key (bytes): Public key of the server
        cid (int): 
        host (str):
        url (str): URL of the server API.

    Returns:
        any: Response from the server
    """
    # Generate a new random key for AES cipher
    aes_key = get_random_bytes(32)

    # Encrypt AES key with public key of Enclave
    encrypted_aes_key = encrypt(public_key, aes_key)

    # Encrypt data for the server using the AES key
    cipher = AES.new(aes_key, AES.MODE_EAX)
    data_cbor = cbor2.dumps(parameter)
    ciphertext, tag = cipher.encrypt_and_digest(data_cbor)

    # Build a message object for the server with element required
    # for decryption and verification
    msg_obj = {
        'encrypted_key': encrypted_aes_key,
        'nonce': cipher.nonce,
        'tag': tag,
        'ciphertext': ciphertext
    }

    # Send message to server and wait for response
    resp_obj = send_request_to_enclave(action=action, parameter=msg_obj,
                                       cid=cid, host=host, api=api)

    # Decrypt the response
    cipher = AES.new(aes_key, AES.MODE_EAX, resp_obj['nonce'])
    response_obj = cipher.decrypt_and_verify(resp_obj['ciphertext'], resp_obj['tag'])

    return cbor2.loads(response_obj)


def get_attestation(cid: int=0, host: str='', api: str='') -> bytes:
    """Request attestation from the server running in the Nitro enclave.

    Args:
        cid (int, optional): Context identifier of the Nitro enclave. Default to 0.
        host (str, optional): Host address of the enclave simulator. Default to ''.
        url (str, optional): URL of the server API. Default to ''.

    Returns:
        bytes: Attestation document.
    """
    response = send_request_to_enclave(action='get-attestation', parameter='',
                                       cid=cid, host=host, api=api)

    if not response:
        print('Unable to get attestation. Cannot continue.')
        exit(0)
    attestation_doc = response['data']
    pprint(base64.b64encode(attestation_doc).decode(), 'Base64 encoded attestation')

    if 'private_key' in response:
        # Displays the private key
        private_key = response['private_key']
        print(f'RSA private key:\n"{private_key.decode()}"')
    return attestation_doc


def send_request_to_enclave(action: str, parameter: any=None, cid:int=0,
                            host:str='', api: str='') -> any:
    """Send a request and optional parameter to a Nitro enclave specified
    by its context identifier (CID), the IP address of the enclave simulator
    or the API URL of a server.

    Args:
        action (str): Request string.
        parameter (any, optional): Parameter of the request. Defaults to None.
        cid (int, optional): context identifier of the Nitro enclave. Default to 0.
        host (str, optional): Host address of the enclave simulator. Default to ''.
        url (str, optional): URL of the server API. Default to ''.

    Returns:
        any: response from the Nitro enclave.
    """
    assert(cid or host or api)

    # Encode the request and parameter
    payload_cbor = cbor2.dumps({
        'action': action,
        'parameter': parameter
    })

    # Send them to the server
    # Create a vsock socket object
    soc = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)

    # Connect to the server running in the Nitro enclave
    soc.connect((cid, VSOCK_PORT))

    pprint(payload_cbor, 'Payload')
    soc.send(base64.b64encode(payload_cbor))
    pprint(f'Sent request to {cid if cid else host}')
    # Receive the response from the server
    payload_b64 = soc.recv(65536)

    # Close the connection with the server
    soc.close()

    pprint(payload_b64, 'Base64 encoded payload')

    response_obj_cbor = base64.b64decode(payload_b64)

    # Decode the response from the server
    response = cbor2.loads(response_obj_cbor)
    pprint(response, 'Response')

    return response
