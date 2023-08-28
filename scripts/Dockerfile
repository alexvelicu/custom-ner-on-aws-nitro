# Create a Docker container for the simple server application
#
#

FROM public.ecr.aws/amazonlinux/amazonlinux:2

# Install python for running the server and net-tools for modifying network config
RUN yum install python3 net-tools -y

WORKDIR /app

COPY requirements.txt ./
RUN pip3 install -r /app/requirements.txt

# Copy the pre-compiled NSM library
COPY libnsm.so ./

# Copy necesary Python files
COPY config.py ./
COPY nsmutil.py ./
COPY server.py ./
COPY ner_api.py ./

# Add language models
ADD models ./models

COPY run-app.sh ./
RUN chmod +x run-app.sh

# Start the server
CMD ["/app/run-app.sh"]
