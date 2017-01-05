# -*- coding:utf-8 -*-
from flask import Flask

app = Flask(__name__)


@app.route('/')
def index():
    from utils import cheese
    cheese()
    return 'Yet another hello!'


if __name__ == '__main__':
    app.run()
