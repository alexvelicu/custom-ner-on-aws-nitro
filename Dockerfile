# Create a Docker container for the simple server application
#
#

FROM public.ecr.aws/amazonlinux/amazonlinux:2

# Install python for running the server and net-tools for modifying network config
RUN yum install python3 net-tools -y

WORKDIR /app

# Install required libraries
COPY requirements.txt ./
RUN pip3 install -r /app/requirements.txt

# Copy necesary Python files including model and libnsm library
COPY src/server.py ./
COPY src/common ./common
COPY src/server ./server
COPY scripts/run-app.sh ./
RUN chmod +x run-app.sh

# Start the server
CMD ["/app/run-app.sh"]
