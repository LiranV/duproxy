# DuProxy - Request duplicator reverse proxy server

## About the implementation
I've started this task by looking for some off-the-shelf solutions that might solve this problem
of spreading POST request to multiple servers.
The closest tool I've found was [goreplay](https://goreplay.org/), but it wasn't enough.  
Because I'm not familiar with Go, I didn't try to alter it's code to suit my needs.  
So I've decided to write my own solution from scratch.
I chose Python + Tornado tornado for the job because I feel most comfortable writing Python.  
After researching some web frameworks, I've picked Tornado because of it's one-threaded-non-blocking
fashion and relative ease of use (I didn't use it before).

While learning to work with Tornado, I've implemented the Round-Robin LB because it was easier for
me than doing the POST handling.  
I've decided to keep this part instead of using a well-known LB for the GET requests.  
This is only due to convenience and I'm well aware that in real environment, using Nginx for example
to load balance the GET requests and only proxy POST requests to this application would be way faster
and more reliable.


## How I tested my code
I've ran multiple instances of a simple REST server I've written with Flask and connected
them to the proxy.
This could probably have been done more efficiently with unit tests.


## Some known problems
- Not using a Nginx / Haproxy to LB "GET" requests
- Request with methods other than "GET" and "POST" are not supported
- Not enough metrics
- Not the most informative logging
- Code can be structured in a more object-oriented way

## How to run
```bash
# Create venv and then install Python requirements
> pip install -r requirements.txt

# Create an inventory file with each one of your host servers written in a new line
# You can use simple_server.py as mock application servers and the sample inventory
> ./simple_server.py 8080 & ./simple_server.py 8081 & ./simple_server.py 8082
> ./duproxy.py -i inventory.conf.sample -p 8000

# For help and more options
> ./duproxy.py -h
```
