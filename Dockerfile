# The build recipe for this app's own image.
#
# Start from a small official Python, install the dependencies, copy the
# code in, and say which command runs the server. Anyone who builds this
# gets the exact same environment -- that is the whole point of Docker.

FROM python:3.12-slim

WORKDIR /app

# Copy requirements.txt on its own first. Docker caches each step, and a
# step is only re-run when its inputs change -- so editing main.py does
# not re-download every dependency. Copying the code first would throw
# that cache away on every single edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3000

# 0.0.0.0, not 127.0.0.1: inside a container, 127.0.0.1 means "only this
# container", so the port mapping would reach nothing.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
