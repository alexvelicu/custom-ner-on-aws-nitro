#!/bin/bash
#
# Use --export option to build an enclave that exports private key with attestation

parent_path=$( cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd -P )
cd "$parent_path"

cert_cn="AWS"
cert_c="US"
cert_st="WA"
cert_l="Seattle"
cert_o="Amazon"
cert_ou="AWS"

key=nitro-test-signing-key.pem
csr=nitro-test-enclave-csr.pem
cert=nitro-test-certificate.pem

eif=spam.eif
enclave_name=spam
image_name=alexandruvelicu/spam

pcr=enclave-description.json

##########
# Change run-app.sh to start server with key export option
##########

if [[ $1 = "--export" ]]; then
    sed -i 's/export_key=False/export_key=True/g' run-app.sh
else
    sed -i 's/export_key=True/export_key=False/g' run-app.sh
fi

##########
# Generate private key and signing certificate to sign the Nitro enclave image
# See: https://docs.aws.amazon.com/enclaves/latest/user/set-up-attestation.html#pcr8
##########

rm $key $csr $cert

# Generate a private key
openssl ecparam -name secp384r1 -genkey -out $key

# Generate a certificate signing request (CSR)
openssl req -new -key $key -sha384 -nodes -subj "/CN=${cert_cn}/C=${cert_c}/ST=${cert_st}/L=${cert_l}/O=${cert_o}/OU=${cert_ou}" -out $csr

# Generate a certificate based on the CSR
openssl x509 -req -days 365  -in $csr -out $cert -sha384 -signkey $key

##########
# Create Nitro enclave
##########

nitro-cli terminate-enclave --enclave-name $enclave_name
rm $eif
docker rmi -f $(docker images -a -q)
#docker build ../ -t nitro-test-enclave:latest
docker pull $image_name:latest
nitro-cli build-enclave \
    --docker-uri $image_name:latest \
    --private-key $key \
    --signing-certificate $cert \
    --output-file $eif

# Get PCR8 value
nitro-cli describe-eif --eif-path $eif > $pcr
mv $pcr ../src/

# TODO: Copy enclave file to remote server with Nitro enclave

nitro-cli run-enclave  \
    --cpu-count 2 --memory 6144  \
    --eif-path $eif --debug-mode  \
    --enclave-cid 16

nitro-cli console --enclave-name $enclave_name