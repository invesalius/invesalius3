import json
import socket

    
def json_serial(filename, mode='r'):
    try:
        with open(filename, mode) as file:
            return json.load(file)
    except Exception as e:
        print("Error: ", e)
        return []
    


def is_valid_ip_address(ip):
    try:
        # Try to parse the input string as an IP address
        ip_address = str(socket.gethostbyname(ip)).strip()
        print("IP ADDRESS: ", ip_address)
        socket.inet_pton(socket.AF_INET, ip_address)
        return True
    except socket.error:
        # If parsing fails, return False
        return False

def is_valid_port(n):
    try:
        n = int(n)
        return 1<= n<= 65535
    except Exception as e:
        return False