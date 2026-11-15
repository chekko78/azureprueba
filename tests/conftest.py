import os

# Para pruebas locales con un SQL Server cuyo certificado firma una CA propia.
if os.getenv("TEST_CA_FILE"):
    import certifi

    certifi.where = lambda: os.environ["TEST_CA_FILE"]
