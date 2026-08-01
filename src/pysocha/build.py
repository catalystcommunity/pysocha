import copy
from datetime import timezone
import dateutil.parser
import jinja2
import math
import os
import re
import shutil
import stat
import tempfile
import uuid

from slugify import slugify

from pysocha.atom import build_atom_feed, build_rss_feed, validate_atom_feed, validate_rss_feed
from pysocha.markdown import parseCommonMark
from pysocha.search import SECTION_PAGES, SECTION_POSTS, build_search_indexes
from pysocha.search.text import split_text_and_code
from pysocha.search.types import SearchRecord


class ContentBuildError(RuntimeError):
    pass


def _document_text(content: str, regions=None):
    """Collect the prose and the code of one document, in template order.

    Regions are rendered separately, so they have to be gathered as well or a
    rich page contributes nothing to the index.
    """
    parts = [content or ""]
    if regions:
        parts.extend(str(value) for value in regions.values())
    prose_parts = []
    code_parts = []
    for part in parts:
        prose, code = split_text_and_code(part)
        if prose:
            prose_parts.append(prose)
        if code:
            code_parts.append(code)
    return "\n".join(prose_parts), "\n".join(code_parts)


def _markdown_options(config: dict) -> dict:
    return config.get('markdown', {})


def _display_output_path(config: dict, output_filename: str) -> str:
    staged_root = os.path.abspath(config['outputDir'])
    relative_path = os.path.relpath(os.path.abspath(output_filename), staged_root)
    return os.path.join(config.get('_displayOutputDir', config['outputDir']), relative_path)


def _render_template(template, context: dict, source_path: str) -> str:
    try:
        return template.render(context)
    except jinja2.UndefinedError as error:
        raise ContentBuildError(
            f"{source_path}: failed to render {template.name}: {error}"
        ) from error


def _parse_post_date(value):
    posted_date = dateutil.parser.parse(value)
    if posted_date.tzinfo is None:
        return posted_date.replace(tzinfo=timezone.utc)
    return posted_date.astimezone(timezone.utc)


def strip_markdown_extension(filename: str) -> str:
    """
    Remove the .md suffix from a source file name.

    This has to remove the suffix, not a set of characters. "diagram.md" must
    become "diagram", and the page URL and the link replacement map must agree,
    or links point at files that do not exist.
    """
    if filename.endswith('.md'):
        return filename[:-len('.md')]
    return filename


def get_markdown_files(directory):
    """
    This function is used to get all the markdown files in a directory
    """
    files = []
    for file in os.listdir(directory):
        if file.endswith('.md'):
            files.append(file)
    return files

def _post_search_record(blog_config: dict, blog_post: dict) -> SearchRecord:
    """Describe one blog post for the search index."""
    prose, code = _document_text(blog_post.get('content'), blog_post.get('content_regions'))
    meta = {'title': blog_post['Title']}
    if blog_post.get('Author'):
        meta['author'] = str(blog_post['Author'])
    hook = blog_post.get('hook') or blog_post.get('summary')
    if hook:
        meta['hook'] = str(hook)

    filters = {'section': [SECTION_POSTS]}
    if blog_post.get('Tags'):
        filters['tags'] = [str(tag) for tag in blog_post['Tags']]
    if blog_post.get('Author'):
        filters['author'] = [str(blog_post['Author'])]

    return SearchRecord(
        url='/' + blog_config['blogBaseDir'] + '/' + blog_post['slugify'],
        title=str(blog_post['Title']),
        content=prose,
        code=code,
        section=SECTION_POSTS,
        date=blog_post.get('PostedDate'),
        meta=meta,
        filters=filters,
    )


def generate_blog_posts(config: dict, verbose: bool = False):
    """
    We go through all blog posts and their related optional outputs like tags or authors, depending on config

    Returns the search records for every listed post.
    """

    templateDir = config['templatesDir']
    templateLoader = jinja2.FileSystemLoader(searchpath=templateDir)
    templateEnv = jinja2.Environment( loader=templateLoader )
    strictTemplateEnv = templateEnv.overlay(undefined=jinja2.StrictUndefined)
    template = templateEnv.get_template(config['blogConfig']['blogTemplate'])
    strict_template = strictTemplateEnv.get_template(config['blogConfig']['blogTemplate'])
    outputDir = os.path.join(os.getcwd(), config['outputDir'])

    posts = {}
    sorted_posts = []
    posts_dir = os.path.join(config['contentDir'], 'blog_posts')
    
    # First we need to get all the content and frontmatter into posts for later
    for post in get_markdown_files(posts_dir):
        source_path = os.path.join(posts_dir, post)
        with open(source_path, 'r') as f:
            file = f.read()
            mark = parseCommonMark(file, _markdown_options(config), source=source_path)
        post_data = mark['frontmatter']
        post_data['PostedDate'] = _parse_post_date(post_data['PostedDate'])
        post_template = strict_template if 'content_regions' in mark else template
        # If we override the template for that page, here it gets invoked
        if 'Template' in mark['frontmatter']:
            environment = strictTemplateEnv if 'content_regions' in mark else templateEnv
            post_template = environment.get_template(mark['frontmatter']['Template'])
        # Same with file extension, which opens some nice scripting possibilities
        file_ext = mark['frontmatter'].get('Extension', config['defaultExtension'])
        post_data['slugify'] = slugify(mark['frontmatter']['Title']) + file_ext
        output_filename = os.path.join(outputDir + '/' + config['blogConfig']['blogBaseDir'] + '/' + post_data['slugify'])
        # This will give all frontmatter and the content to the jinja template
        post_data['content'] = mark['markdown']
        if 'content_regions' in mark:
            post_data['content_regions'] = mark['content_regions']
        post_data['rendered'] = _render_template(post_template, post_data, source_path)
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
    search_records = []
    for blog_post in sorted_posts:
        output_filename = os.path.join(output_dir, blog_post['slugify'])
        if verbose:
            print(_display_output_path(config, output_filename))
        with open(output_filename, 'w+') as f:
            f.write(blog_post['rendered'])

        search_records.append(_post_search_record(blog_config, blog_post))

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
        if verbose:
            print(_display_output_path(config, output_filename))
        with open(output_filename, 'w+') as f:
            f.write(listing_template.render({'posts': listings[offset:offset+page_limit],
                                             'all_posts': sorted_posts,
                                             'title': blog_config['title'],
                                             'page_num': page_num,
                                             'total_pages': total_pages}))

    output_filename = os.path.join(output_dir, 'tags' + file_ext)
    if verbose:
        print(_display_output_path(config, output_filename))
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
            if verbose:
                print(_display_output_path(config, output_filename))
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
    if verbose:
        print(_display_output_path(config, output_filename))
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
                if verbose:
                    print(_display_output_path(config, output_filename))
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
            if verbose:
                print(_display_output_path(config, output_filename))
            with open(output_filename, 'w+') as f:
                f.write(author_template.render({'author': author,
                                                'all_posts': sorted_posts,
                                                'title': 'Posts for author: ' + author,
                                                'posts': posts}))

    sorted_posts.sort(key=lambda post: post['PostedDate'], reverse=True)
    if blog_config['atomFeeds']:
        feed_author = first_author
        if feed_author is None and sorted_posts:
            feed_author = sorted_posts[0].get('Author')
        atom_feed = build_atom_feed(
            config['siteTitle'],
            config['siteAddress'],
            blog_config['blogBaseDir'],
            sorted_posts,
            feed_author,
        )
        validate_atom_feed(atom_feed)
        output_filename = os.path.join(config['outputDir'], blog_config['blogBaseDir'], 'atom.xml')
        if verbose:
            print(_display_output_path(config, output_filename))
        with open(output_filename, 'w+') as f:
            f.write(atom_feed)
        if not blog_config.get('disableRSS', False) and all(post.get('AuthorEmail') for post in sorted_posts):
            rss_feed = build_rss_feed(
                config['siteTitle'],
                config['siteAddress'],
                blog_config['blogBaseDir'],
                sorted_posts,
            )
            validate_rss_feed(rss_feed)
            output_filename = os.path.join(config['outputDir'], blog_config['blogBaseDir'], 'rss.xml')
            if verbose:
                print(_display_output_path(config, output_filename))
            with open(output_filename, 'w+') as f:
                f.write(rss_feed)

    return search_records

def generate_pages(config: dict, verbose: bool = False):
    """
    We go through all the possibilities for generating any page related details

    Returns the search records for every page.
    """
    templateDir = config['templatesDir']
    templateLoader = jinja2.FileSystemLoader(searchpath=templateDir)
    templateEnv = jinja2.Environment( loader=templateLoader )
    strictTemplateEnv = templateEnv.overlay(undefined=jinja2.StrictUndefined)
    template = templateEnv.get_template(config['pageConfig']['pageDefaultTemplate'])
    strict_template = strictTemplateEnv.get_template(config['pageConfig']['pageDefaultTemplate'])
    outputDir = os.path.join(os.getcwd(), config['outputDir'])

    pages = {}
    search_records = []
    pages_dir = os.path.join(config['contentDir'], 'pages')
    for page in get_markdown_files(pages_dir):
        pages[page] = {}
        source_path = os.path.join(pages_dir, page)
        with open(source_path, 'r') as f:
            file = f.read()
            mark = parseCommonMark(file, _markdown_options(config), source=source_path)
        page_template = strict_template if 'content_regions' in mark else template
        # If we override the template for that page, here it gets invoked
        if 'Template' in mark['frontmatter']:
            environment = strictTemplateEnv if 'content_regions' in mark else templateEnv
            page_template = environment.get_template(mark['frontmatter']['Template'])
        # Same with file extension, which opens some nice scripting possibilities
        file_ext = mark['frontmatter'].get('Extension', config['defaultExtension'])
        pages[page]['slugify'] = strip_markdown_extension(page)
        output_filename = os.path.join(outputDir + '/' + pages[page]['slugify'] + file_ext)
        if verbose:
            print(_display_output_path(config, output_filename))
        # This will give all frontmatter and the content to the jinja template
        context = mark['frontmatter']
        context['content'] = mark['markdown']
        if 'content_regions' in mark:
            context['content_regions'] = mark['content_regions']
        with open(output_filename, 'w+') as f:
            foo = _render_template(page_template, context, source_path)
            foo = config['_pattern'].sub(lambda m: config['_replacements'][m.group(0)], foo)
            f.write(foo)

        if not context.get('Unlisted'):
            prose, code = _document_text(context.get('content'), mark.get('content_regions'))
            title = str(context.get('Title') or pages[page]['slugify'])
            search_records.append(SearchRecord(
                url='/' + pages[page]['slugify'] + file_ext,
                title=title,
                content=prose,
                code=code,
                section=SECTION_PAGES,
                meta={'title': title},
                filters={'section': [SECTION_PAGES]},
            ))

    return search_records

def generate_extras(config: dict):
    """
    EVERY site should have extra files, even if it's just CSS or JS files, so process them here very simply
    """
    extra_files_dir = os.path.join(config['contentDir'], 'extra_files')
    output_dir = os.path.join(config['outputDir']) 
    shutil.copytree(extra_files_dir, output_dir, dirs_exist_ok=True)

def generate_search(config: dict, records: list, verbose: bool = False):
    """
    Build every configured search index, and render the search page of each one
    that names a template. This runs inside the staged output, so a failed index
    never replaces a good site.
    """
    if not config.get('search'):
        return []

    templateEnv = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath=config['templatesDir']))

    def render_page(instance, context, assets):
        template = templateEnv.get_template(instance.template)
        page = {
            'name': instance.name,
            'path': instance.path,
            'url': context.instance_url,
            'provider': instance.provider,
            'scripts': assets.scripts,
            'styles': assets.styles,
            'data': assets.data,
        }
        output_filename = os.path.join(context.instance_dir, 'index' + config['defaultExtension'])
        if verbose:
            print(_display_output_path(config, output_filename))
        with open(output_filename, 'w+') as f:
            f.write(_render_template(
                template,
                {'search': page, 'title': config['siteTitle'], 'site': config['siteTitle']},
                f"search:{instance.name}",
            ))

    return build_search_indexes(config, records, render_page=render_page, verbose=verbose)


def build_pages_replacement_map(config: dict) -> dict:
    """
    We need to replace instances of things like "index.md" with "index.html" anywhere it's reference in markdown, so
    just build a map for pages here ahead of the markdown conversion
    """
    pages_dir = os.path.join(config['contentDir'], 'pages')
    replacements = {}
    for page in get_markdown_files(pages_dir):
        replacements[page] = strip_markdown_extension(page) + config['defaultExtension']
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
        source_path = os.path.join(pages_dir, page)
        with open(source_path, 'r') as f:
            file = f.read()
            mark = parseCommonMark(file, _markdown_options(config), source=source_path)
        replacements[page] = config['blogConfig']['blogBaseDir'] + '/' + slugify(mark['frontmatter']['Title']) + config['defaultExtension']
    return replacements

def _publish_staged_output(staged_output: str, output_dir: str):
    parent = os.path.dirname(output_dir)
    backup = None
    if os.path.exists(output_dir):
        backup = os.path.join(
            parent,
            f".{os.path.basename(output_dir)}.pysocha-backup-{uuid.uuid4().hex}",
        )
        os.replace(output_dir, backup)

    try:
        os.replace(staged_output, output_dir)
    except Exception:
        if backup is not None and not os.path.exists(output_dir):
            os.replace(backup, output_dir)
        raise
    else:
        if backup is not None:
            shutil.rmtree(backup)


def buildSite(config: dict, verbose: bool = False):
    output_dir = os.path.abspath(config['outputDir'])
    working_dir = os.path.abspath(os.getcwd())
    if output_dir in {os.path.abspath(os.sep), working_dir}:
        raise ValueError("outputDir must not be the filesystem root or the working directory")

    output_mode = (
        stat.S_IMODE(os.stat(output_dir).st_mode)
        if os.path.isdir(output_dir)
        else 0o755
    )
    output_parent = os.path.dirname(output_dir)
    os.makedirs(output_parent, exist_ok=True)
    staged_output = tempfile.mkdtemp(
        prefix=f".{os.path.basename(output_dir)}.pysocha-build-",
        dir=output_parent,
    )
    build_config = copy.deepcopy(config)
    build_config['outputDir'] = staged_output
    build_config['_displayOutputDir'] = config['outputDir']

    try:
        pages_map = build_pages_replacement_map(build_config)
        posts_map = build_posts_replacement_map(build_config)
        overlapping_names = sorted(pages_map.keys() & posts_map.keys())
        if overlapping_names:
            names = ", ".join(overlapping_names)
            raise ContentBuildError(
                f"pages and blog posts have overlapping source names: {names}"
            )
        # Now that we have the maps, we can build the replacements and the pattern for regex on all files
        build_config['_replacements'] = {**pages_map, **posts_map}
        rep = dict((re.escape(k), v) for k, v in build_config['_replacements'].items())
        build_config['_pattern'] = re.compile("|".join(rep.keys()))
        generate_extras(build_config)
        search_records = generate_pages(build_config, verbose=verbose)
        search_records += generate_blog_posts(build_config, verbose=verbose)
        generate_search(build_config, search_records, verbose=verbose)
        os.chmod(staged_output, output_mode)
        _publish_staged_output(staged_output, output_dir)
    finally:
        if os.path.exists(staged_output):
            shutil.rmtree(staged_output)
    return
