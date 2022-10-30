FROM python:3.9-bullseye

# install from pypi
WORKDIR /app
RUN pip install ntfsdump

# you can rewrite this command when running the docker container.
# ex. docker run --rm -v $(pwd):/app -t ntfsdump:latest '/$MFT' /app/sample.raw
ENTRYPOINT ["ntfsdump"]
CMD ["-h"]
