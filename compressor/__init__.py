#!/usr/bin/env python

"""
Base class and common functions for compressor implementations.
"""

# pylint: disable=W0311

class BaseProcessor(object):
  "Base class for compression processors."
  def __init__(self, options, is_request, params):
    self.options = options
    self.is_request = is_request
    self.params = params

  def compress(self, in_headers, host):
    """
    'in_headers' are the headers that will be processed. They are expected
    to be a dictionary whose keys are header names (all lowercase), and
    whose values are strings. Multiple instances of a header field will
    be delimited by \0 (null) characters.
    
    There are a number of special header names, indicated by ':' as the
    first character in the name.

    'host' is the host header value for the request (or associated request,
    if it is a response).
       
    Return value is the resulting compressed headers.
    """
    raise NotImplementedError

  def decompress(self, compressed):
    """
    'compressed' is the compressed headers.
       
    Return value is a header dictionary, as described above.
    """
    raise NotImplementedError
    
    
def format_http1(frame, delimiter="\r\n", valsep=": ", host='host'):
  """Take the frame and format it as HTTP/1"""
  out_frame = []
  top_line = ''
  avoid_list = []
  if ':method' in frame:
    top_line = '%s %s %s%s' % (
        frame[':method'], frame[':path'], frame[':version'], delimiter)
    avoid_list = [':method', ':path', ':version', ':scheme']
  else:
    top_line = '%s %s %s%s' % (
        frame[':version'], frame[':status'], frame[':status-text'], delimiter)
    avoid_list = [':version', ':status', ':status-text']
  out_frame.append(top_line)
  
  for (key, val) in frame.iteritems():
    if key in avoid_list:
      continue
    if key == ':host':
      key = host
    for individual_val in val.split('\x00'):
      out_frame.append(key)
      out_frame.append(valsep)
      out_frame.append(individual_val)
      out_frame.append(delimiter)
  out_frame.append(delimiter)
  return ''.join(out_frame)
  
  
def strip_conn_headers(hdrs):
  """Remove hop-by-hop headers from a header dictionary."""
  hop_by_hop = ['transfer-encoding', 'te', 'keep-alive', 'trailers']
  if hdrs.has_key('connection'):
    hop_by_hop.extend([v.strip() for v in hdrs['connection'].split(None)])
    del hdrs['connection']
  for hdr in hop_by_hop:
    try:
      del hdrs[hdr]
    except KeyError:
      pass
  return hdrs


def parse_http1(message):
  """Take a HTTP1 message and return the header structure for it."""
  out = {}
  lines = message.strip().split("\n")
  top_line = lines.pop(0).split(None, 2)
  for line in lines:
    if not line: 
      break
    name, value = line.split(":", 1)
    name = name.lower()
    if out.has_key(name):
      out[name] += "\0" + value.strip()
    else:
      out[name] = value.strip()
  if "host" in out.keys():
    out[":scheme"] = "http" # FIXME: find https?
    out[':method'] = top_line[0]
    out[':path'] = top_line[1]
    out[':version'] = top_line[2].strip()
    out[':host'] = out['host']
    del out['host']
  else:
    out[':version'] = top_line[0]
    out[':status'] = top_line[1]
    out[':status-text'] = top_line[2].strip()
  return out