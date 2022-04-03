import copyreg
import pickle, ssl, socket

context = ssl.SSLContext()
context.load_cert_chain('./server.cert', './server_priv.key')
context.load_verify_locations(capath='./cacert.pem')

def save_socket(obj):
    return obj.__class__, (obj.__dict__,)

def save_ssl_context(obj):
    return obj.__class__, (obj.protocol,)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock = context.wrap_socket(sock, do_handshake_on_connect=False)
copyreg.pickle(ob_type=ssl.SSLSocket, pickle_function=save_socket)
copyreg.pickle(ssl.SSLContext, save_ssl_context)
test = pickle.dumps(sock)
test2 = pickle.loads(test)
type(test2)