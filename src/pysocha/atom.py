


ATOM_HEADER="""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
"""
ATOM_FEED_ELEMENTS="""
  <title>{siteTitle}</title>
  <link href="{siteAddress}"/>
  <updated>{updatedDate}</updated>
  <author>
    <name>{author}</name>
  </author>
  <id>{siteAddress}</id>
"""
ATOM_ENTRY="""
  <entry>
    <title>{Title}</title>
    <author>
      <name>{authorName}</name>
    </author>
    <link href="{siteAddress}{blogBaseDir}/{slugify}"/>
    <id>{siteAddress}{blogBaseDir}/{slugify}</id>
    <updated>{updatedDate}</updated>
    <summary>{hook}</summary>
  </entry>
"""
ATOM_FOOTER="""
</feed>
"""


