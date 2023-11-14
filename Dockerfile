FROM python:3.11-bullseye
WORKDIR /app

# install dependencies
RUN pip install -U pip && pip install poetry
RUN poetry config virtualenvs.create false

# install application
RUN poetry install

# you can rewrite this command when running the docker container.
# ex. docker run --rm -v $(pwd):/app -t ntfsdump:latest '/$MFT' /app/sample.raw
ENTRYPOINT ["poetry", "run", "python", "-m" "ntfsdump"]
CMD ["-h"]
