#!/usr/bin/env python3

import argparse
import logging
import sys
import random
import prometheus_client as pc
import tornado.httpserver
import tornado.httpclient
import tornado.web
import tornado.iostream
import tornado.ioloop
import tornado.httputil
from tornado import gen

servers = []

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger("DuProxy")

SRC_CLIENT = "client"
SRC_PROXY = "proxy"

http_requests_counter = pc.Counter("http_requests_total",
                                            "Total number of incoming HTTP requests by source",
                                            ["method", "source"])

http_responses_counter = pc.Counter("http_responses_total",
                                         "Total number of HTTP responses by source",
                                         ["code", "source"])


def gen_request_with_new_host(src_req, new_host):
    url = src_req.protocol + "://" + new_host + src_req.uri
    body = None if src_req.method == "GET" else src_req.body
    return tornado.httpclient.HTTPRequest(
        url,
        method=src_req.method,
        headers=tornado.httputil.HTTPHeaders(src_req.headers),
        body=body
    )


class MainHandler(tornado.web.RequestHandler):
    rr = 0

    @gen.coroutine
    def http_request_until_success(self, request, max_backoff=10000):
        """Send an HTTP request and return the response.
        Uses truncated exponential backoff wait time for the delay between retries.
        Keeps trying until success.

        max_backoff - The maximum backoff time in milliseconds.
        """
        num_of_tries = 0
        http_client = tornado.httpclient.AsyncHTTPClient()
        while (True):
            try:
                http_requests_counter.labels(method=request.method.lower(), source=SRC_PROXY).inc()
                response = yield http_client.fetch(request)
                http_responses_counter.labels(code=response.code, source=SRC_CLIENT).inc()
                return response
            except (IOError, tornado.httpclient.HTTPError) as e:
                if isinstance(e, tornado.httpclient.HTTPError):
                    http_responses_counter.labels(code=e.response.code, source=SRC_CLIENT).inc()
                logger.error("[{} <--{}-- {}] {}".format("proxy", request.method, request.url, e))

                # backoff
                backoff_time_ms = random.randint(0, (2**num_of_tries)-1)
                if (backoff_time_ms > max_backoff):
                    backoff_time_ms = max_backoff
                backoff_time_seconds = backoff_time_ms / 1000
                num_of_tries += 1
                logger.debug("Backoff for {} ms".format(backoff_time_ms))
                yield gen.sleep(backoff_time_seconds)

    @gen.coroutine
    def on_finish(self):
        http_requests_counter.labels(method=self.request.method.lower(), source=SRC_CLIENT).inc()


    @gen.coroutine
    def get(self):
        r = self.request
        logger.debug("Round robin turn: {}".format(MainHandler.rr))
        request = gen_request_with_new_host(r, servers[MainHandler.rr])
        MainHandler.rr = (MainHandler.rr + 1) % len(servers)
        http_client = tornado.httpclient.AsyncHTTPClient()
        try:
            http_requests_counter.labels(method=request.method.lower(), source=SRC_PROXY).inc()
            response = yield http_client.fetch(request)
            http_responses_counter.labels(code=response.code, source=SRC_CLIENT).inc()
        except tornado.httpclient.HTTPError as e:
            logger.debug("[{} <--{}-- {}] {}".format("proxy", request.method, request.url, e))
            http_responses_counter.labels(code=e.response.code, source=SRC_CLIENT).inc()
            response = e.response
        except IOError as e:
            logger.error("Error: {}".format(e))
            http_responses_counter.labels(code=503, source=SRC_PROXY).inc()
            self.send_error(503)
            return

        self.clear()
        for name, value in response.headers.get_all():
            self.set_header(name, value)
        self.set_status(response.code)
        self.write(response.body)
        self.finish()


    @gen.coroutine
    def post(self):
        response_sent = False
        r = self.request
        request_futures = [self.http_request_until_success(
            gen_request_with_new_host(r, servers[i])) for i in range(len(servers))
        ]
        wait_iterator = gen.WaitIterator(*request_futures)

        # Act on the first successful response
        while not wait_iterator.done():
            try:
                result = yield wait_iterator.next()
            except Exception as e:
                logger.error("Error {} from {}".format(e, wait_iterator.current_future))

            # Return the first response
            if (not response_sent):
                self.clear()
                for name, value in result.headers.get_all():
                    self.set_header(name, value)
                self.set_status(result.code)
                self.write(result.body)
                self.finish()
                http_responses_counter.labels(code=result.code, source=SRC_PROXY).inc()

                response_sent = True
                logger.debug("First successful response received from '{}', and was returned to client.".format(
                    servers[wait_iterator.current_index]))


def read_inventory(path="inventory.conf"):
    """Read the confing file containing all the servers that should be served.
    Returnes the list of servers.
    """
    try:
        with open(path, "r") as f:
                servers_list = f.read().splitlines()
    except OSError as e:
        sys.exit("Cannot load inventory file from '{}': {}".format(path, e.strerror))
    return servers_list


def main(options):
    pc.start_http_server(options.metrics_port)
    logger.info("Metrics server running on port {}.".format(options.metrics_port))
    global servers
    servers = read_inventory(options.inventory_path)
    # Turn off 'debug' mode for production
    app = tornado.web.Application([
        (r"/.*", MainHandler),
    ], debug=True)
    http_server = tornado.httpserver.HTTPServer(app)
    http_server.listen(options.port)
    logger.info("DuProxy server running on port {}.".format(options.port))
    try:
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        logger.info("Bye!")


if __name__ == "__main__":
    desc_text = ("Incoming POST requests will be forwarded to all the servers behind this proxy.\n"
                 "First successful response will be returned to the client while the other"
                 "forwarded requests are being retried until succeeding."
                 )
    parser = argparse.ArgumentParser(
        description="DuProxy - Request duplicator reverse proxy server",
        epilog=desc_text
    )
    parser.add_argument("-p",
                        "--port",
                        dest="port",
                        type=int,
                        default=80,
                        help="Port number for the proxy to listen on"
                        )
    parser.add_argument("-i",
                        "--inventory-path",
                        dest="inventory_path",
                        type=str,
                        default="inventory.conf",
                        help="Path to the inventory file which holds the hosts (one host per line)"
                        )
    parser.add_argument("-m",
                        "--metrics-port",
                        dest="metrics_port",
                        type=int,
                        default=9000,
                        help="Port number for the metrics server"
                        )
    options = parser.parse_args()
    main(options)
