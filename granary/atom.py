"""Convert ActivityStreams to Atom.

Atom spec: http://atomenabled.org/developers/syndication/
"""

import collections
import os
import re
import urlparse
import xml.sax.saxutils

from bs4 import BeautifulSoup
import jinja2
from oauth_dropins.webutil import util

import microformats2
import source

ATOM_TEMPLATE_FILE = 'user_feed.atom'
# stolen from django.utils.html
UNENCODED_AMPERSANDS_RE = re.compile(r'&(?!(\w+|#\d+);)')


def _encode_ampersands(text):
  return UNENCODED_AMPERSANDS_RE.sub('&amp;', text)


def activities_to_atom(activities, actor, title=None, request_url=None,
                       host_url=None):
  """Converts ActivityStreams activites to an Atom feed.

  Args:
    activities: list of ActivityStreams activity dicts
    actor: ActivityStreams actor dict, the author of the feed
    title: string, the feed <title> element. Defaults to 'User feed for [NAME]'
    request_url: the URL of this Atom feed, if any. Used in a link rel="self".
    host_url: the home URL for this Atom feed, if any. Used in the top-level
      feed <id> element.

  Returns: unicode string with Atom XML
  """
  # Strip query params from URLs so that we don't include access tokens, etc
  host_url = (_remove_query_params(host_url) if host_url
              else 'https://github.com/snarfed/granary')
  request_url = _remove_query_params(request_url) if request_url else host_url

  for a in activities:
    act_type = source.object_type(a)
    if not act_type or act_type == 'post':
      primary = a.get('object', {})
    else:
      primary = a
    obj = a.setdefault('object', {})
    # Render content as HTML; escape &s
    rendered = []

    rendered.append(microformats2.render_content(primary))
    obj['rendered_content'] = _encode_ampersands('\n'.join(rendered))

    # Make sure every activity has the title field, since Atom <entry> requires
    # the title element.
    if not a.get('title'):
      a['title'] = util.ellipsize(_encode_ampersands(
        a.get('displayName') or a.get('content') or obj.get('title') or
        obj.get('displayName') or obj.get('content') or 'Untitled'))

    # strip HTML tags. the Atom spec says title is plain text:
    # http://atomenabled.org/developers/syndication/#requiredEntryElements
    a['title'] = xml.sax.saxutils.escape(
      BeautifulSoup(a['title'], 'html.parser').get_text(''))

    # Normalize attachments.image to always be a list.
    for att in primary.get('attachments', []):
      image = att.get('image')
      if image and not isinstance(image, list):
        att['image'] = [image]

  # Emulate Django template behavior that returns a special default value that
  # can continue to be referenced when an attribute or item lookup fails. Helps
  # avoid conditionals in the template itself.
  # https://docs.djangoproject.com/en/1.8/ref/templates/language/#variables
  class Defaulter(collections.defaultdict):
    def __init__(self, **kwargs):
      super(Defaulter, self).__init__(Defaulter, **{
        k: (Defaulter(**v) if isinstance(v, dict) else v)
        for k, v in kwargs.items()})

    def __unicode__(self):
      return super(Defaulter, self).__unicode__() if self else u''

  env = jinja2.Environment(loader=jinja2.PackageLoader(__package__, 'templates'),
                           autoescape=True)
  if actor is None:
    actor = {}
  return env.get_template(ATOM_TEMPLATE_FILE).render(
    items=[Defaulter(**a) for a in activities],
    host_url=host_url,
    request_url=request_url,
    title=title or 'User feed for ' + source.Source.actor_name(actor),
    updated=activities[0]['object'].get('published', '') if activities else '',
    actor=Defaulter(**actor),
    )


def _remove_query_params(url):
  parsed = list(urlparse.urlparse(url))
  parsed[4] = ''
  return urlparse.urlunparse(parsed)
