FROM python:3.13-slim
WORKDIR /app

# install dependencies
RUN pip install -U pip && pip install uv

# install application
COPY . /app
RUN uv sync

# you can rewrite this command when running the docker container.
# ex. docker run --rm -v $(pwd):/app -t ntfsdump:latest '/$MFT' /app/sample.raw
ENTRYPOINT ["uv", "run", "ntfsdump"]
CMD ["-h"]
