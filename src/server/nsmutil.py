"""
AWS Nitro Test

Modified NSMUtil class from the NitroPepper project to interface in Python with
the Nitro Enclave NSM API.

See:
https://github.com/donkersgoed/nitropepper-enclave-app
https://github.com/donkersgoed/aws-nitro-enclaves-nsm-api
"""
import base64
import Crypto
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP

from common.config import RSA_PRIVATE_KEY, ATTESTATION
import server.libnsm as libnsm  # pylint: disable=import-error


class NSMUtil():
    """NSM util class."""

    def __init__(self, simulate: bool):
        """Construct a new NSMUtil instance."""
        # If True, simulate presence of Nitro enclave
        self._simulate = simulate

        if simulate:
            # Import a pre-computed RSA private key whose public
            # key is present in a signed Enclave attestation
            self._rsa_key = RSA.import_key(RSA_PRIVATE_KEY)
        else:
            # Initialize the Rust NSM Library
            self._nsm_fd = libnsm.nsm_lib_init() # pylint:disable=c-extension-no-member
            # Create a new random function `nsm_rand_func`, which
            # utilizes the NSM module.
            self.nsm_rand_func = lambda num_bytes : libnsm.nsm_get_random( # pylint:disable=c-extension-no-member
                self._nsm_fd, num_bytes
            )

            # Force pycryptodome to use the new rand function.
            # Without this, pycryptodome defaults to /dev/random
            # and /dev/urandom, which are not available in Enclaves.
            self._monkey_patch_crypto(self.nsm_rand_func)

            # Generate a new RSA certificate, which will be used to
            # generate the Attestation document and to decrypt results
            # for KMS Decrypt calls with this document.
            self._rsa_key = RSA.generate(4096)

        # Derive public key from private key
        self._public_key = self._rsa_key.publickey().export_key('DER')

    def get_attestation_doc(self):
        """Get the attestation document from /dev/nsm."""
        if self._simulate:
            # Use a pre-computed attestation
            libnsm_att_doc_cose_signed = base64.b64decode(ATTESTATION)
        else:
            # TODO: Update interface to be able to specify nonce
            # See: https://github.com/donkersgoed/aws-nitro-enclaves-nsm-api/commit/112a450082d108bf466ca57e687beaaeff19db4a
            libnsm_att_doc_cose_signed = libnsm.nsm_get_attestation_doc( # pylint:disable=c-extension-no-member
                self._nsm_fd,
                self._public_key,
                len(self._public_key)
            )
        return libnsm_att_doc_cose_signed

    def decrypt(self, ciphertext: bytes) -> bytes:
        """Decrypt ciphertext using private key"""
        cipher = PKCS1_OAEP.new(self._rsa_key)
        plaintext = cipher.decrypt(ciphertext)

        return plaintext

    @classmethod
    def _monkey_patch_crypto(cls, nsm_rand_func):
        """Monkeypatch Crypto to use the NSM rand function."""
        Crypto.Random.get_random_bytes = nsm_rand_func
        def new_random_read(self, n_bytes): # pylint:disable=unused-argument
            return nsm_rand_func(n_bytes)
        Crypto.Random._UrandomRNG.read = new_random_read # pylint:disable=protected-access
