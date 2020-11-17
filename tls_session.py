import socket
from client_messages import ClientHello, ClientKeyExchange, \
    ClientChangeCipherSpec, ClientFinished, ClientApplicationData
from server_messages import ServerHello, ServerCertificate, \
    ServerKeyExchange, ServerDone, ServerChangeCipherSpec, ServerFinished, ServerApplicationData
from key_exchange import X25519
from ciphers import AES_GCM
from crypto_utils import PRF, randomBytes, sha256


class TlsSession():
    
    def __init__(self, hostname, port=443):
        self.hostname = hostname
        self.port = port
        # Initialise a socket for an IPv4, TCP connection
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ip = socket.gethostbyname(hostname)
        self.client_random = randomBytes(32)
        self.record = b''

    def connect(self):
        print("Trying to connect...")
        self.socket.connect((self.ip, self.port))
        print(f"Connected to {self.ip}.")
        self._handshake()

    def _handshake(self): 
        self._sendHello()
        self._recvHello()
        self._recvCertificate()
        self._recvKeyExchange()
        self._recvHelloDone()
        # TODO: Check certificate
        #self._verifyCertificate()
        self._calculateKeys()
        self._sendKeyExchange()
        self._sendFinished()
        self._recvFinished()
    
    def send(self, data: bytes):
        self.client_seq_num = self._incrementSeqNum(self.client_seq_num)
        additional_data = self.client_seq_num + b'\x17\x03\x03' + len(data).to_bytes(2, byteorder='big')
        ciphertext = self.encryptor.encrypt(self.client_seq_num, data, additional_data)
        application_data = ClientApplicationData(self.client_seq_num, ciphertext)

        self.socket.send(bytes(application_data))
        print("Sent")

    def recv(self) -> bytes:
        self.server_seq_num = self._incrementSeqNum(self.server_seq_num)
        application_data = ServerApplicationData()
        application_data.parseFromStream(self.socket)
        additional_data = self.server_seq_num + b'\x17\x03\x03' + len(application_data.ciphertext).to_bytes(2, byteorder='big')
        plaintext = self.decryptor.decrypt(application_data.nonce, application_data.ciphertext, additional_data)
        return plaintext


    def _sendHello(self):
        hello = ClientHello(random=self.client_random, hostname=self.hostname)
        self.socket.send(bytes(hello))
        self.record += hello.data

    def _recvHello(self):
        serv_hello = ServerHello()
        serv_hello.parseFromStream(self.socket)
        self.server_random = serv_hello.random
        self.record += serv_hello.data

    def _recvCertificate(self):
        serv_cert = ServerCertificate()
        serv_cert.parseFromStream(self.socket)
        self.record += serv_cert.data

    def _recvKeyExchange(self):
        serv_key_ex = ServerKeyExchange()
        serv_key_ex.parseFromStream(self.socket)
        self.server_key = serv_key_ex.public_key
        self.record += serv_key_ex.data

    def _recvHelloDone(self):
        serv_done = ServerDone()
        serv_done.parseFromStream(self.socket)
        self.record += serv_done.data

    def _sendKeyExchange(self):
        client_key_ex = ClientKeyExchange(self.public_key)
        self.socket.send(bytes(client_key_ex))
        self.record += client_key_ex.data
        
    def _sendFinished(self):
        client_change_cipher = ClientChangeCipherSpec()
        self.socket.send(bytes(client_change_cipher))

        # TODO: Don't just hardcode this 
        record_hash = self._PRF_HandshakeRecord()
        self.client_seq_num = bytes(8)
        self.server_seq_num = bytes(8)

        self.encryptor = AES_GCM(self.client_key, self.client_IV)
        
        additional_data = self.client_seq_num + b'\x16\x03\x03\x00\x10' 
        payload = b'\x14\x00\x00\x0c' + record_hash 
        ciphertext = self.encryptor.encrypt(self.client_seq_num, payload, additional_data)


        client_finished = ClientFinished(self.client_seq_num, ciphertext)
        self.socket.send(bytes(client_finished))

    def _recvFinished(self):

        serv_change_cipher = ServerChangeCipherSpec()
        serv_change_cipher.parseFromStream(self.socket)

        serv_finished = ServerFinished()
        serv_finished.parseFromStream(self.socket)

        self.decryptor = AES_GCM(self.server_key, self.server_IV)

        additional_data = self.server_seq_num + b'\x16\x03\x03\x00\x10'
        plaintext = self.decryptor.decrypt(serv_finished.nonce, serv_finished.ciphertext, additional_data)

        print(plaintext)

        #TODO: Verify plaintext is correct


    def _incrementSeqNum(self, seq_num: bytes) -> bytes:
        # We can't increment bytes directly in python so we convert to int and back
        inc_seq_num = int.from_bytes(self.client_seq_num, byteorder='big') + 1
        return inc_seq_num.to_bytes(8, byteorder='big')

    def _calculateKeys(self):
        key_exchange = X25519()
        self.public_key = key_exchange.publicKey()
        master_secret, expanded_key = key_exchange.computeExpandedMasterSecret(
                self.server_key, self.client_random, self.server_random)
        self.master_secret = master_secret
        # The way we partition the master secret is unique to our ciphersuite.
        self.client_key = expanded_key[:16]
        self.server_key = expanded_key[16:32]
        self.client_IV = expanded_key[32:36]
        self.server_IV = expanded_key[36:40]

    def _PRF_HandshakeRecord(self) -> bytes:
        return PRF(secret = self.master_secret,
                   label = b'client finished',
                   seed = sha256(self.record),
                   num_bytes = 12)

def testSession():
    data = b'ping'

    session = TlsSession("localhost", port=44330)
    session.connect()
    session.send(data)
    res = session.recv()
    print(res)
    
if __name__ == "__main__":
    testSession()
    

