"""
AWS Nitro Test

Utility functions for verifying AWS Nitro attestation documents
"""
import re
import tempfile
import os
import zipfile
from urllib.parse import urlparse
from cryptography import x509

from pycose.keys.ec2 import EC2Key as EC2
from pycose.keys.curves import P384
from pycose.messages import Sign1Message
import requests

#from cose import EC2, CoseAlgorithms, CoseEllipticCurves
from OpenSSL import crypto as sslcrypto

from common.config import AWS_NITRO_CERT


def get_aws_root_cert() -> str:
    """Get the PEM content of the AWS Nitro Enclave root certificate

    Returns:
        str: Root certificate PEM content
    """
    url_elements = urlparse(AWS_NITRO_CERT)
    zip_filename = os.path.basename(url_elements.path)

    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir_name:

        # Download the ZIP file containing the certificate and save to file
        with open (os.path.join(tmp_dir_name, zip_filename), "wb") as file:
            file.write(requests.get(AWS_NITRO_CERT, timeout=3).content)

        # Decompress the ZIP file
        with zipfile.ZipFile(os.path.join(tmp_dir_name, zip_filename), "r") as zip_ref:
            zip_ref.extractall(tmp_dir_name)

        # Load the content of the certificate from file
        with open(os.path.join(tmp_dir_name, 'root.pem'), mode = 'r', encoding= 'ascii') as file:
            aws_root_cert_pem = file.read()

    return aws_root_cert_pem


def check_attestation_document(attestation_doc_obj: dict,
                               public_key: bool = False,
                               user_data: bool = False,
                               nonce: bool = False):
    """Verify the fields of an Attestation Document. Optional fields are checked if
    the corresponding input parameter is set to True.
    See: https://github.com/aws/aws-nitro-enclaves-nsm-api/blob/main/docs/attestation_process.md

    Args:
        attestation_doc_obj (dict): Attestation document array.
        public_key (bool, optional): If True, check the public key field. Defaults to False.
        user_data (bool, optional): If True, check the user_data field. Defaults to False.
        nonce (bool, optional): If True, check the nonce field. Defaults to False.
    """
    mandatory_fields = ["module_id", "digest", "timestamp", "pcrs", "certificate", "cabundle"]
    authorised_pcr_lengths = [32, 48, 64]
    authorised_digests = ['SHA384']

    for field in mandatory_fields:
        assert field in attestation_doc_obj.keys(), f'Missing field: {field}'

        assert isinstance(attestation_doc_obj['module_id'], str) \
           and len(attestation_doc_obj['module_id']) != 0, \
           'Empty module ID'

    assert isinstance(attestation_doc_obj['digest'], str) \
           and attestation_doc_obj['digest'] in authorised_digests, \
           'Wrong digest'

    assert isinstance(attestation_doc_obj['timestamp'], int) \
           and attestation_doc_obj['timestamp'] > 0, \
           'Timestamp must be greater than 0'

    assert isinstance(attestation_doc_obj['pcrs'], dict) \
           and len(attestation_doc_obj['pcrs']) >= 1 \
           and len(attestation_doc_obj['pcrs']) <= 32, \
           'There should be at least one and at most 32 PCR fields'

    for index, value in attestation_doc_obj['pcrs'].items():
        assert isinstance(index, int), \
            'PCR indices should be integers'
        assert isinstance(value, bytes), \
            'PCR content must be a byte string'
        assert len(value) in authorised_pcr_lengths, \
            f'Length of PCR can be one of these values: {authorised_pcr_lengths}'

    assert isinstance(attestation_doc_obj['cabundle'], list), \
        'CA Bundle should be a list'
    assert len(attestation_doc_obj['cabundle']) > 0, \
        'CA Bundle should not be empty'

    for element in attestation_doc_obj['cabundle']:
        assert isinstance(element, bytes), \
            'CA bundle entry must have byte string type'
        assert len(element) >= 1 and len(element) <= 1024, \
            'CA bundle entry must have length between 1 and 1024'

    if public_key:
        assert 'public_key' in attestation_doc_obj.keys(), \
            'Public key not present in attestation document'
        assert isinstance(attestation_doc_obj['public_key'], bytes) \
               and len(attestation_doc_obj['public_key']) >= 1 \
               and len(attestation_doc_obj['public_key']) <= 1024, \
               'Public key must be a string between 1 and 1024 bytes'

    if user_data:
        assert 'user_data' in attestation_doc_obj.keys(), \
            'User data key not present in attestation document'
        assert isinstance(attestation_doc_obj['user_data'], bytes) \
               and len(attestation_doc_obj['user_data']) >= 0 \
               and len(attestation_doc_obj['user_data']) <= 512, \
               'User data must be a string between 0 and 512 bytes'

    if nonce:
        assert 'nonce' in attestation_doc_obj.keys(), \
            'Nonce not present in attestation document'
        assert isinstance(attestation_doc_obj['nonce'], bytes) \
               and len(attestation_doc_obj['nonce']) >= 0 \
               and len(attestation_doc_obj['nonce']) <= 512, \
               'Nonce must be a string between 0 and 512 bytes'

    print('Valid attestation')


def verify_certificate(attestation_doc_obj: dict, cert: sslcrypto.X509):
    """Verify the signing certificate of an attestation document.

    Args:
        attestation_doc_obj (dict): Attestation document array
        cert (sslcrypto.X509): Certificate of the key used to sign the attestation
    """
    # Get the AWS root certificate
    aws_root_cert_pem = get_aws_root_cert()

    # Create an X509Store object for the CA bundles
    store = sslcrypto.X509Store()

    # This first CA in the CA bundle should be the AWS root certificate
    # Create the CA cert object from PEM string, and store into X509Store
    aws_root_cert = sslcrypto.load_certificate(sslcrypto.FILETYPE_PEM, aws_root_cert_pem)
    store.add_cert(aws_root_cert)

    # Get the interim and target certificate from CA bundle and add them to the X509Store
    # Except the first certificate, which is the root certificate and which has been
    # replaced by the known one (above)
    for intermediary_cert_binary in attestation_doc_obj['cabundle'][1:]:
        intermediary_cert = sslcrypto.load_certificate(sslcrypto.FILETYPE_ASN1,
                                                       intermediary_cert_binary)
        store.add_cert(intermediary_cert)

    # Get the X509Store context
    store_ctx = sslcrypto.X509StoreContext(store, cert)

    # Validate the certificate
    # If the cert is invalid, it will raise exception
    try:
        store_ctx.verify_certificate()
    except sslcrypto.X509StoreContextError as error:
        print(f'Certificate not valid. {error}')
        return

    print('Valid AWS signing certificate')


def verify_signature(cose_sign_obj: list, cert: x509):
    """Verify the the signature of the attestation document
    See:
    https://www.rfc-editor.org/rfc/rfc8152
    https://github.com/aws/aws-nitro-enclaves-nsm-api/blob/main/docs/attestation_process.md
    https://pycose.readthedocs.io/en/latest/pycose/messages/sign1message.html
    https://github.com/awslabs/aws-nitro-enclaves-cose/blob/main/src/sign.rs

    Args:
        cose_sign_obj (list): COSE Sign1 object
        cert (X509): Certificate of the signing key

    Raises:
        Exception: Generic exception if the signature is not correct
    """
    # Get the key parameters from the certificate's public key
    cert_public_numbers = cert.public_key().public_numbers()

    # Create the EC2 key from public key parameters
    key = EC2(x = cert_public_numbers.x.to_bytes(48, 'big'),
            y = cert_public_numbers.y.to_bytes(48, 'big'),
            crv = P384)

    # Construct the Sign1 message
    sign1_msg = Sign1Message.from_cose_obj(cose_sign_obj, True)
    sign1_msg.key = key

    # Verify the signature using the EC2 key
    if not sign1_msg.verify_signature():  # pylint:  disable=no-member
        raise Exception('Wrong signature')

    print('Valid signature on attestation document')


def verify_pcrs(attestation_doc_obj: dict, eif_description: dict) -> None:
    """Verify that a PCR in the attestation matches a given value

    Args:
        attestation_doc_obj (object): Attestation document array
        index (int): Index of the PCR to check
        pcr_val (str): Expected PCR value

    Raises:
        Exception: Raises an exception if verification fails
    """
    for pcr_index, pcr_val in eif_description['Measurements'].items():
        result = re.findall(r'PCR(\d)', pcr_index)
        if result:
            index = int(result[0])
            if attestation_doc_obj['pcrs'][index].hex() != pcr_val:
                print(f'Wrong PCR{index}. Expecting {pcr_val[0:30]}... '
                                f'got {attestation_doc_obj["pcrs"][index].hex()[0:30]}...')
            else:
                print(f'PCR{index} valid: {pcr_val[0:30]}')
