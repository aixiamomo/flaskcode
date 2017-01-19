from multiprocessing import Process
import os


def run_proc(name):
    print 'Run child process {} ({}).'.format(name, os.getpid())


print 'Parent process {}.'.format(os.getpid())
p = Process(target=run_proc, args=('test',))
print 'Process will start.'
p.start()
p.join()
print 'Process end.'
