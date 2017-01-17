# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os.path

from tornado.testing import AsyncTestCase
from tornado.httpclient import AsyncHTTPClient
from tornado.websocket import websocket_connect
from tornado.ioloop import IOLoop
import html5lib

from httpwatcher import HttpWatcherServer

from .utils import *

import json
import logging


class TestHttpWatcherServer(AsyncTestCase):

    temp_path = None
    watcher_server = None
    expected_livereload_js = read_resource(os.path.join("scripts", "livereload.js"))

    def setUp(self):
        super(TestHttpWatcherServer, self).setUp()

        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s\t%(name)s\t%(levelname)s\t%(message)s',
        )

        self.temp_path = init_temp_path()
        write_file(
            self.temp_path,
            "index.html",
            "<!DOCTYPE html><html><head><title>Hello world</title></head>" +
            "<body>Test</body></html>"
        )

    def test_watching(self):
        self.watcher_server = HttpWatcherServer(
            self.temp_path,
            host="localhost",
            port=5555,
            watcher_interval=0.1
        )
        self.watcher_server.listen()
        self.exec_watch_server_tests("")
        self.watcher_server.shutdown()

    def test_watching_non_standard_base_path(self):
        self.watcher_server = HttpWatcherServer(
            self.temp_path,
            host="localhost",
            port=5555,
            watcher_interval=0.1,
            server_base_path="/non-standard/"
        )
        self.watcher_server.listen()
        self.exec_watch_server_tests("/non-standard/")
        self.watcher_server.shutdown()

    def exec_watch_server_tests(self, base_path):
        client = AsyncHTTPClient()
        client.fetch("http://localhost:5555"+base_path, self.stop)
        response = self.wait()

        self.assertEqual(200, response.code)
        html = html5lib.parse(response.body)
        ns = get_html_namespace(html)
        self.assertEqual("Hello world", html_findall(html, ns, "./{ns}head/{ns}title")[0].text.strip())

        script_tags = html_findall(html, ns, "./{ns}body/{ns}script")
        self.assertEqual(2, len(script_tags))
        self.assertEqual("http://localhost:5555/livereload.js", script_tags[0].attrib['src'])
        self.assertEqual('livereload("ws://localhost:5555/livereload");', script_tags[1].text.strip())

        # if it's a non-standard base path
        if len(base_path.strip("/")) > 0:
            # we shouldn't be able to find anything at the root base path
            client.fetch("http://localhost:5555/", self.stop)
            response = self.wait()
            self.assertEqual(404, response.code)

        # fetch the livereload.js file
        client.fetch("http://localhost:5555/livereload.js", self.stop)
        response = self.wait()

        self.assertEqual(200, response.code)
        self.assertEqual(self.expected_livereload_js, response.body)

        # now connect via WebSockets
        websocket_connect("ws://localhost:5555/livereload").add_done_callback(
            lambda future: self.stop(future.result())
        )
        websocket_client = self.wait()

        # trigger a watcher reload
        write_file(self.temp_path, "README.txt", "Hello world!")

        IOLoop.current().call_later(
            0.5,
            lambda: websocket_client.read_message(lambda future: self.stop(future.result()))
        )
        msg = json.loads(self.wait())
        self.assertIn("command", msg)
        self.assertEqual("reload", msg["command"])
