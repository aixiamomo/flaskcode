from werkzeug.local import LocalStack, LocalProxy, Local
import time
from threading import Thread

pseudo_global_data = Local()


# should print 999
def data_setter_1(value):
    pseudo_global_data.value = value
    time.sleep(5)
    print 'data_setter_1: ', pseudo_global_data.value
    return 0


# should print 1000
def data_setter_2(value):
    pseudo_global_data.value = value
    print 'data_setter_2: ', pseudo_global_data.value
    return 0

if __name__ == '__main__':
    t1 = Thread(target=data_setter_1, args=(999,))
    t2 = Thread(target=data_setter_2, args=(1000,))
    t1.start()
    time.sleep(2)
    t2.start()