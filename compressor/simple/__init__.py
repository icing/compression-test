
# pylint: disable=W0311

from .. import BaseProcessor, strip_conn_headers, format_http1, parse_http1
from collections import defaultdict
import re
import calendar
from email.utils import parsedate as lib_parsedate
from email.utils import formatdate as lib_formatdate
from urlparse import urlsplit
import os.path  
from copy import copy

class Processor(BaseProcessor):
  """
  This compressor does a few things, compared to HTTP/1:

  * It compares the current set of outgoing headers to the last set on
    the connection. If a header has the same value (character-for-character),
    a reference to it is sent in the 'ref' header instead.

  * Common header names are tokenised using the lookups table. If a header
    name does not occur there, its name will be preceded with a "!".

  * Header types that are known to be dates are expressed as a hexidecimal
    number of seconds since the epoch.    
    
  * "\n" is used as a line delimiter, instead of "\r\n".
  
  * No space is inserted between the ":" and the start of the header value.
  """

  lookups = {
    'x-content-type-options': 'xct',
    'content-encoding': 'ce', 
    'access-control-allow-origin': 'ac',
    'content-type': 'ct',
    'accept-language': 'al', 
    'accept-encoding': 'ae', 
    'accept-ranges': 'ar',
    'user-agent': 'ua',
    'server': 's',
    'referer': 'r',
    'accept': 'a',
    'cookie': 'c',
    'last-modified': 'lm',
    'cache-control': 'cc',
    'pragma': 'p',
    'vary': 'v',
    'date': 'd',
    'expires': 'x',
    'content-length': 'cl',
    'etag': 'e',
    'content-language': 'la',
    'via': 'vi',
    'set-cookie': 'sc',
    'p3p': 'p3',
  }
  
  date_hdrs = [
    'last-modified',
    'date',
    'expires'
  ]
  
  def __init__(self, options, is_request, params):
    BaseProcessor.__init__(self, options, is_request, params)
    self.last_c = None
    self.last_d = None
    self.rev_lookups = {v:k for k, v in self.lookups.items()}
    assert len(self.lookups) == len(self.rev_lookups)

  def compress(self, in_headers, host):
    headers = {}
    refs = []
    for name, value in strip_conn_headers(in_headers).items():
      if name in self.date_hdrs:
        try:
          headers[self.hdr_name(name)] = "%x" % parse_date(value)
        except ValueError:
          headers[self.hdr_name(name)] = value
      elif self.last_c \
      and name[0] != ":" \
      and self.last_c.get(name, None) == value:
#      and (name[0] != ":" or name == ':host') \
#        if name == ':host':
#          name = 'h'
        refs.append(name)
      else:
        headers[self.hdr_name(name)] = value
    self.last_c = in_headers
    if refs:
      headers["ref"] = ",".join([self.hdr_name(ref) for ref in refs])
    out = []
    return format_http1(headers, delimiter="\n", valsep=":", host='host')
  

  def decompress(self, compressed):
    headers = parse_http1(compressed)
    out_headers = {}
    for name in headers.keys():
      if name == "ref":
        continue
      elif name[0] == ":":
        out_headers[name] = headers[name]
      elif name[0] == '!':
        out_headers[name[1:]] = headers[name]
      else:
        expanded_name = self.rev_lookups[name]
        if expanded_name in self.date_hdrs:
          try:
            out_headers[expanded_name] = format_date(int(headers[name], 16))
          except ValueError:
            out_headers[expanded_name] = headers[name]
        else:
          out_headers[expanded_name] = headers[name]
    if headers.has_key('ref') and self.last_d:
      refs = headers['ref'].split(",")
      for ref in refs:
        if ref[0] == "!":
          name = ref[1:]
        else:
          name = self.rev_lookups[ref]
        try:
          out_headers[name] = self.last_d[name]
        except KeyError:
          import sys
          sys.stdout.write("\n\n%s\n\n" % repr(self.last_d))
          raise
    self.last_d = copy(out_headers)
    return out_headers

  def hdr_name(self, name):
    if name[0] == ":":
      return name
    return self.lookups.get(name, "!%s" % name)



DATE = r"""(?:\w{3},\ [0-9]{2}\ \w{3}\ [0-9]{4}\ [0-9]{2}:[0-9]{2}:[0-9]{2}\ GMT |
         \w{6,9},\ [0-9]{2}\-\w{3}\-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2}\ GMT |
         \w{3}\ \w{3}\ [0-9 ][0-9]\ [0-9]{2}:[0-9]{2}:[0-9]{2}\ [0-9]{4})
        """
        
def parse_date(value):
    """Parse a HTTP date. Raises ValueError if it's bad."""
    if not re.match(r"%s$" % DATE, value, re.VERBOSE):
        raise ValueError
    date_tuple = lib_parsedate(value)
    if date_tuple is None:
        raise ValueError
    # http://sourceforge.net/tracker/index.php?func=detail&aid=1194222&group_id=5470&atid=105470
    if date_tuple[0] < 100:
        if date_tuple[0] > 68:
            date_tuple = (date_tuple[0]+1900,)+date_tuple[1:]
        else:
            date_tuple = (date_tuple[0]+2000,)+date_tuple[1:]
    date = calendar.timegm(date_tuple)
    return date
    
def format_date(value):
  """Format a HTTP date."""
  return lib_formatdate(timeval=value, localtime=False, usegmt=True)