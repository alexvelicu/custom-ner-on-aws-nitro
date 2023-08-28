"""
AWS Nitro Test

Helper functions
"""
import json
import pprint as PPrint
import subprocess

import cbor2

from click import Option, UsageError
from cryptography import x509

from common.attestation import check_attestation_document, verify_certificate, verify_pcrs, \
    verify_signature
from common.config import ENCLAVE_NAME, MAX_LENGTH


class MutuallyExclusiveOption(Option):
    """Click class to specify mutually exclusive options"""
    def __init__(self, *args, **kwargs):
        self.mutually_exclusive_with = set(kwargs.pop('mutually_exclusive_with', []))
        help = kwargs.get('help', '')  # pylint: disable=redefined-builtin
        if self.mutually_exclusive_with:
            ex_str = ', '.join(self.mutually_exclusive_with)
            kwargs['help'] = help + (
                ' Note: This argument is mutually exclusive with arguments: [' + ex_str + '].'
            )
        super(MutuallyExclusiveOption, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if self.mutually_exclusive_with.intersection(opts) and self.name in opts:
            raise UsageError(
                f"Illegal usage: '{self.name}' is mutually exclusive with "
                f"arguments '{', '.join(self.mutually_exclusive_with)}'.")

        return super(MutuallyExclusiveOption, self).handle_parse_result(
            ctx,
            opts,
            args
        )


class PPrintTruncated(PPrint.PrettyPrinter):
    """pprint class to trunc long strings"""
    def _format(self, object, *args, **kwargs):  # pylint: disable=redefined-builtin
        if isinstance(object, bytes):
            if len(object) > MAX_LENGTH:
                object = object[:MAX_LENGTH] + b'...'
        if isinstance(object, str):
            if len(object) > MAX_LENGTH:
                object = object[:MAX_LENGTH] + '...'
        return PPrint.PrettyPrinter._format(self, object, *args, **kwargs)  # pylint: disable=protected-access


def pprint(value: any, name: str='') -> None:
    """Pretty print any value trimming long strings.

    Args:
        value (any): Value to be printed.
        name (str, optional): Name of the value. Defaults to ''.
    """
    formatted_value = PPrintTruncated().pformat(value)
    if name:
        print(f'{name}: {formatted_value}')
    else:
        print(formatted_value)


def get_cid(enclave_name: str = ENCLAVE_NAME) -> int:
    """Get CID of a running enclave.

    Args:
        enclave_name (str, optional): Name of the enclave. Defaults to ENCLAVE_NAME.

    Returns:
        (int): Enclave CID is successful. 0 otherwise.
    """
    try:
        enclaves_str = subprocess.check_output(['nitro-cli', 'describe-enclaves'])
    except:
        return 0
    if not enclaves_str:
        return 0

    enclaves_obj = json.loads(enclaves_str)
    cid = 0
    for enclave in enclaves_obj:
        if enclave['EnclaveName'] == enclave_name:
            cid = enclave['EnclaveCID']

    return cid


def verify_enclave(eif_description_file: str, attestation_doc: bytes) -> bytes:
    """Verify that a remote enclave is valid.

    Args:
        eif_description_file (str): Name of file containing an expected EIF description
        attestation_doc (bytes): Attestation document of an enclave

    Returns:
        bytes: RSA public key of the enclave if verification successful
    """
    # Load COSE Sign1 object
    cose_sign_obj = cbor2.loads(attestation_doc)

    # Get the payload from the COSE object which contains public key and certificate
    # See: https://github.com/aws/aws-nitro-enclaves-nsm-api/blob/main/docs/attestation_process.md
    attestation_doc_obj = cbor2.loads(cose_sign_obj[2])

    # Shows the content of the attestation
    pprint(attestation_doc_obj, 'Attestation')

    # Check that the attestation document contains the mandatory fields
    check_attestation_document(attestation_doc_obj, public_key = True)
    enclave_public_key = attestation_doc_obj['public_key']

    # Get signing certificate from attestation document
    cert = x509.load_der_x509_certificate(attestation_doc_obj['certificate'])

    # Verify PCR8 of the enclave
    if eif_description_file != '':
        eif_description = None
        with open(eif_description_file, mode = 'r', encoding= 'utf-8') as file:
            eif_description = json.load(file)
        verify_pcrs(attestation_doc_obj, eif_description)

    # Verify signing certificate
    verify_certificate(attestation_doc_obj, cert)

    # Verify signature
    verify_signature(cose_sign_obj, cert)
    return enclave_public_key
