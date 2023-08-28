"""
AWS Nitro Test

Server application that runs in a Nitro enclave
"""
import base64
import json
import socket
import pprint

import cbor2
import click

from Crypto.Cipher import AES

from common.config import BASTION_HOST, VSOCK_PORT
from common.helper import pprint, MutuallyExclusiveOption
from server.ner_api import MODELS, MODEL_NAMES, get_data, InputModel, ResponseModel
from server.nsmutil import NSMUtil


@click.command()
@click.option('--simulate', cls=MutuallyExclusiveOption, type=bool, default=False,
              help='If set to True, simulate a Nitro enclave. Default is False.',
              mutually_exclusive_with=['export'])
@click.option('--export', cls=MutuallyExclusiveOption, type=bool, default=False,
               help="If set to True, returns RSA private key with attestation. "
               "For debugging only. Default is False.",
               mutually_exclusive_with=['simulate'])
def main(simulate: bool, export: bool):
    """Main server application meant to run in AWS Nitro enclave"""
    print("Starting server...")

    # Initialise NSMUtil
    nsm_util = NSMUtil(simulate)
    if simulate:
        print('Simulating presence of Nitro enclave.')
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.bind((BASTION_HOST, VSOCK_PORT))
    else:
        # Create a vsock socket object
        client_socket = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)  # pylint: disable=no-member

        # Listen for connection from any CID
        cid = socket.VMADDR_CID_ANY  # pylint: disable=no-member

        # Bind the socket to CID and port
        client_socket.bind((cid, VSOCK_PORT))

    # Listen for connection from the client
    client_socket.listen()

    print("Server started...")

    while True:
        client_connection, addr = client_socket.accept()
        print('New connection accepted from %s', addr)

        # Get command from client and decode it
        payload_cbor = client_connection.recv(4096)
        request = cbor2.loads(payload_cbor)

        print('Received request: %s', request)

        if request['action'] == 'get-attestation':
            # Generate attestation document
            response_obj = {'attestation': nsm_util.get_attestation_doc()}  # pylint: disable=used-before-assignment
            if export:
                response_obj['private_key'] = nsm_util._rsa_key.export_key()  # pylint: disable=protected-access

        else:
            # Extract the content of the message
            msg_obj = request['parameter']

            # Decrypt the encrypted AES key using the private of the server
            encrypted_aes_key = msg_obj['encrypted_key']
            aes_key = nsm_util.decrypt(encrypted_aes_key)

            cipher = AES.new(aes_key, AES.MODE_EAX, msg_obj['nonce'])
            data_cbor = cipher.decrypt_and_verify(msg_obj['ciphertext'], msg_obj['tag'])
            data = cbor2.loads(data_cbor)
            pprint(data, 'Data received')

            # Prepare response depending on required action
            if request['action'] == 'message':
                # Add some message to the received message
                response = data + ' - Added by server'


            elif request['action'] == 'models':
                # Provide the list of available NER models
                response = MODEL_NAMES

            elif request['action'] == 'process':
                data_obj = json.loads(data)
                query = InputModel(**data_obj)
                nlp = MODELS[query.model]
                response_body = []
                texts = (text.content for text in query.texts)
                for doc in nlp.pipe(texts):
                    response_body.append(get_data(doc))
                response_obj = {"result": response_body}
                response = ResponseModel(**response_obj).json()

            else:
                response = 'Unknown action request.'

            # Encode response with CBOR
            response_cbor = cbor2.dumps(response)

            # Encrypt the CBOR encoded response
            cipher = AES.new(aes_key, AES.MODE_EAX)
            ciphertext, tag = cipher.encrypt_and_digest(response_cbor)

            # Build a message object for the server
            response_obj = {
                'nonce': cipher.nonce,
                'tag': tag,
                'ciphertext': ciphertext
            }

        pprint(response_obj, 'Response')

        # Encode the response object with CBOR
        response_obj_cbor = cbor2.dumps(response_obj)
        pprint(response_obj_cbor, 'CBOR encoded response')

        response_b64 = base64.b64encode(response_obj_cbor)
        pprint(response_b64, 'Base64 encoded response')

        # Send CBOR encoded response to client
        client_connection.sendall(response_b64)

        # Close the connection with client
        client_connection.close()

if __name__ == '__main__':
    main()  # pylint: disable=no-value-for-parameter
