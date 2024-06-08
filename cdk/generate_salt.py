import os

# Generate a 16-byte random salt
salt = os.urandom(16)

# Convert the salt into a hexadecimal string for storage
hex_salt = salt.hex()

# Write the hexadecimal salt to a file
with open("salt.txt", "w", encoding="utf-8") as file:
    file.write(hex_salt)
