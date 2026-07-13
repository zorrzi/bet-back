import random
import string
import base64

def generate_random_password(length=12):
    characters = string.ascii_letters + string.digits + string.punctuation
    random_password = ''.join(random.choice(characters) for _ in range(length))
    encoded_password = base64.b64encode(random_password.encode()).decode()
    return encoded_password

if __name__ == "__main__":
    print(generate_random_password())