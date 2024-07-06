from datetime import timezone
import dateutil.parser
import jinja2
import math
import os
import re
import shutil

from slugify import slugify

from pysocha.atom import ATOM_ENTRY, ATOM_FEED_ELEMENTS, ATOM_FOOTER, ATOM_HEADER

from pysocha.markdown import parseCommonMark


def get_markdown_files(directory):
    """
    This function is used to get all the markdown files in a directory
    """
    files = []
    for file in os.listdir(directory):
        if file.endswith('.md'):
            files.append(file)
    return files

def generate_blog_posts(config: dict):
    """
    We go through all blog posts and their related optional outputs like tags or authors, depending on config
    """
    
    templateDir = config['templatesDir']
    templateLoader = jinja2.FileSystemLoader(searchpath=templateDir)
    templateEnv = jinja2.Environment( loader=templateLoader )
    template = templateEnv.get_template(config['blogConfig']['blogTemplate'])
    outputDir = os.path.join(os.getcwd(), config['outputDir'])

    posts = {}
    sorted_posts = []
    posts_dir = os.path.join(config['contentDir'], 'blog_posts')
    
    # First we need to get all the content and frontmatter into posts for later
    for post in get_markdown_files(posts_dir):
        with open(os.path.join(posts_dir, post), 'r') as f:
            file = f.read()
            mark = parseCommonMark(file)
        post_data = mark['frontmatter']
        post_data['PostedDate'] = dateutil.parser.parse(post_data['PostedDate']).replace(tzinfo=timezone.utc)
        post_template = template
        # If we override the template for that page, here it gets invoked
        if 'Template' in mark['frontmatter']:
            post_template = templateEnv.get_template(mark['frontmatter']['Template'])
        # Same with file extension, which opens some nice scripting possibilities
        file_ext = mark['frontmatter'].get('Extension', config['defaultExtension'])
        post_data['slugify'] = slugify(mark['frontmatter']['Title']) + file_ext
        output_filename = os.path.join(outputDir + '/' + config['blogConfig']['blogBaseDir'] + '/' + post_data['slugify'])
        # This will give all frontmatter and the content to the jinja template
        post_data['content'] = mark['markdown']
        post_data['rendered'] = post_template.render(post_data)
        post_data['rendered'] = config['_pattern'].sub(lambda m: config['_replacements'][m.group(0)], post_data['rendered'])
        posts[post] = post_data
        if post_data.get('Unlisted') is None:
            sorted_posts.append(post_data)

    sorted_posts.sort(key=lambda post: post['PostedDate'], reverse=config['descending'])
    blog_config = config['blogConfig']
    listing_template = blog_config['listingTemplate']
    listings = []
    tags_template = blog_config['tagsTemplate']
    tag_template = blog_config['tagTemplate']
    tags = {}
    authors_template = blog_config['authorsTemplate']
    author_template = blog_config['authorTemplate']
    authors = {}
    output_dir = os.path.join(config['outputDir'], blog_config['blogBaseDir'])
    file_ext = config['defaultExtension']
    os.makedirs(output_dir, exist_ok=True)

    # We'll need to make all the blog posts
    for blog_post in sorted_posts:
        output_filename = os.path.join(output_dir, blog_post['slugify'])
        with open(output_filename, 'w+') as f:
            f.write(blog_post['rendered'])

        # Now populate lists, first one only if the post has all the keys needed for a listing
        listings.append(blog_post)
        # Make a list of posts for each tag out there
        if tags_template and tag_template and blog_post.get('Tags'):
            for tag in blog_post['Tags']:
                if tag not in tags:
                    tags[tag] = []
                tags[tag].append(blog_post)
        # Make a list of posts for each author out there
        if authors_template and author_template and blog_post.get('Author'):
            if blog_post['Author'] not in authors:
                authors[blog_post['Author']] = []
            authors[blog_post['Author']].append(blog_post)

    # Make them templates objects
    listing_template = templateEnv.get_template(listing_template)
    tags_template = templateEnv.get_template(tags_template)
    tag_template = templateEnv.get_template(tag_template)
    authors_template = templateEnv.get_template(authors_template)
    author_template = templateEnv.get_template(author_template)

    # Listings, and they need pages
    page_limit = blog_config['listingPaginationNum']
    total_pages = int(math.floor(len(listings) / page_limit) + 1)
    ranges = range(1,  total_pages + (total_pages > 1)) or [1]
    for page_num in ranges:
        file_num = str(page_num) + file_ext
        offset = (page_num - 1) * page_limit
        output_filename = os.path.join(output_dir, 'listing' + file_num)
        with open(output_filename, 'w+') as f:
            f.write(listing_template.render({'posts': listings[offset:offset+page_limit],
                                             'all_posts': sorted_posts,
                                             'title': blog_config['title'],
                                             'page_num': page_num,
                                             'total_pages': total_pages}))

    output_filename = os.path.join(output_dir, 'tags' + file_ext)
    with open(output_filename, 'w+') as f:
        f.write(tags_template.render({'tags': tags, 'title': 'Tags', 'all_posts': sorted_posts}))
    for tag, posts in tags.items():
        page_limit = blog_config['tagPaginationNum']
        total_pages = int(math.floor(len(posts) / page_limit)) + 1
        ranges = range(1,  total_pages + (total_pages > 1)) or [1]
        for page_num in ranges:
            file_num = str(page_num) + file_ext
            offset = (page_num - 1) * page_limit
            tag_file = 'tag_' + tag.replace(' ', '_')
            output_filename = os.path.join(output_dir, tag_file + file_num)
            with open(output_filename, 'w+') as f:
                f.write(tag_template.render({'posts': posts[offset:offset+page_limit],
                                             'all_posts': sorted_posts,
                                             'tag': tag,
                                             'tag_file': tag_file,
                                             'title': 'Posts for tag: ' + tag,
                                             'page_num': page_num,
                                             'total_pages': total_pages}))

    output_filename = os.path.join(output_dir, 'authors' + file_ext)
    first_author = None
    with open(output_filename, 'w+') as f:
        f.write(authors_template.render({'authors': authors, 'title': 'Authors', 'all_posts': sorted_posts}))
    for author, posts in authors.items():
        if first_author is None:
            first_author = author
        if 'authorPaginationNum' in blog_config:
            page_limit = blog_config['authorPaginationNum']
            total_pages = int(math.floor(len(posts) / page_limit) + 1)
            ranges = range(1,  total_pages + (total_pages > 1)) or [1]
            for page_num in ranges:
                file_num = str(page_num) + file_ext
                offset = (page_num - 1) * page_limit
                author_file = 'author_' + author.replace(' ', '_')
                output_filename = os.path.join(output_dir, author_file + file_num)
                with open(output_filename, 'w+') as f:
                    f.write(author_template.render({'author': author,
                                                    'author_file': author_file,
                                                    'title': 'Posts for author: ' + author,
                                                    'posts': posts[offset:offset+page_limit],
                                                    'all_posts': sorted_posts,
                                                    'page_num': page_num,
                                                    'total_pages': total_pages}))
        else:
            output_filename = os.path.join(output_dir, 'author_' + author.replace(' ', '_') + file_ext)
            with open(output_filename, 'w+') as f:
                f.write(author_template.render({'author': author,
                                                'all_posts': sorted_posts,
                                                'title': 'Posts for author: ' + author,
                                                'posts': posts}))

    sorted_posts.sort(key=lambda post: post['PostedDate'], reverse=True)
    if blog_config['atomFeeds']:
        atom_feed = ""
        atom_feed += ATOM_HEADER
        atom_elements = {
            'siteTitle': config['siteTitle'],
            'siteAddress': config['siteAddress'],
            'author': first_author,
            'updatedDate': sorted_posts[0]['PostedDate'].isoformat(),
        }
        atom_feed += ATOM_FEED_ELEMENTS.format(**atom_elements)
        for post in sorted_posts:
            entry = {
                'Title': post['Title'],
                'siteAddress': config['siteAddress'],
                'blogBaseDir': blog_config['blogBaseDir'],
                'slugify': post['slugify'],
                'updatedDate': post['PostedDate'].isoformat(),
                'hook': post.get('hook', post.get('summary', post['Title'])),
                'authorName': post['Author'],
            }
            atom_feed += ATOM_ENTRY.format(**entry)
        atom_feed += ATOM_FOOTER
        output_filename = os.path.join(config['outputDir'], blog_config['blogBaseDir'], 'atom.xml')
        with open(output_filename, 'w+') as f:
            f.write(atom_feed)

def generate_pages(config: dict):
    """
    We go through all the possibilities for generating any page related details
    """
    templateDir = config['templatesDir']
    templateLoader = jinja2.FileSystemLoader(searchpath=templateDir)
    templateEnv = jinja2.Environment( loader=templateLoader )
    template = templateEnv.get_template(config['pageConfig']['pageDefaultTemplate'])
    outputDir = os.path.join(os.getcwd(), config['outputDir'])

    pages = {}
    pages_dir = os.path.join(config['contentDir'], 'pages')
    for page in get_markdown_files(pages_dir):
        pages[page] = {}
        with open(os.path.join(pages_dir, page), 'r') as f:
            file = f.read()
            mark = parseCommonMark(file)
        page_template = template
        # If we override the template for that page, here it gets invoked
        if 'Template' in mark['frontmatter']:
            page_template = templateEnv.get_template(mark['frontmatter']['Template'])
        # Same with file extension, which opens some nice scripting possibilities
        file_ext = mark['frontmatter'].get('Extension', config['defaultExtension'])
        pages[page]['slugify'] = page.rstrip('.md')
        output_filename = os.path.join(outputDir + '/' + pages[page]['slugify'] + file_ext)
        print(output_filename)
        # This will give all frontmatter and the content to the jinja template
        context = mark['frontmatter']
        context['content'] = mark['markdown']
        with open(output_filename, 'w+') as f:
            foo = page_template.render(context)
            foo = config['_pattern'].sub(lambda m: config['_replacements'][m.group(0)], foo)
            f.write(foo)

def generate_extras(config: dict):
    """
    EVERY site should have extra files, even if it's just CSS or JS files, so process them here very simply
    """
    extra_files_dir = os.path.join(config['contentDir'], 'extra_files')
    output_dir = os.path.join(config['outputDir']) 
    shutil.copytree(extra_files_dir, output_dir, dirs_exist_ok=True)

def build_pages_replacement_map(config: dict) -> dict:
    """
    We need to replace instances of things like "index.md" with "index.html" anywhere it's reference in markdown, so
    just build a map for pages here ahead of the markdown conversion
    """
    pages_dir = os.path.join(config['contentDir'], 'pages')
    replacements = {}
    for page in get_markdown_files(pages_dir):
        replacements[page] = page.replace('.md', config['defaultExtension'])
    return replacements

def build_posts_replacement_map(config: dict) -> dict:
    """
    We also need a replacement map for posts, which means we need to replace them with their slugs
    """
    pages_dir = os.path.join(config['contentDir'], 'blog_posts')
    # At some point, if we link to the listings or just the blog base as me, we'll need that in this patterns too,
    # but that's a mistake anyway, as we should be using the default extension and know what we're linking to
    replacements = {}
    for page in get_markdown_files(pages_dir):
        with open(os.path.join(pages_dir, page), 'r') as f:
            file = f.read()
            mark = parseCommonMark(file)
        replacements[page] = config['blogConfig']['blogBaseDir'] + '/' + slugify(mark['frontmatter']['Title']) + config['defaultExtension']
    return replacements

def buildSite(config: dict):
    if os.path.exists(config['outputDir']):
        shutil.rmtree(config['outputDir'])
        os.makedirs(config['outputDir'])
    pages_map = build_pages_replacement_map(config)
    posts_map = build_posts_replacement_map(config)
    # Now that we have the maps, we can build the replacements and the pattern for regex on all files
    config['_replacements'] = {**pages_map, **posts_map}
    rep = dict((re.escape(k), v) for k, v in config['_replacements'].items())
    config['_pattern'] = re.compile("|".join(rep.keys()))
    if len(config['_replacements'].keys()) > len(pages_map.keys()) + len(posts_map.keys()):
        print('Pages and Posts have overlapping names. Please fix this.')
        print('Overlappng names: ', pages_map.keys() & posts_map.keys())
        exit(1)
    generate_extras(config)
    generate_pages(config)
    generate_blog_posts(config)
    return
