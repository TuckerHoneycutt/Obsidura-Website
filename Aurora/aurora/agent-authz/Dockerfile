FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91

# PyJWT[crypto] for RS256/ES256 ID-token verification against the issuer JWKS.
RUN pip install --no-cache-dir "PyJWT[crypto]==2.10.1"

WORKDIR /app
COPY authz.py /app/authz.py

EXPOSE 9140
CMD ["python", "-u", "/app/authz.py"]
