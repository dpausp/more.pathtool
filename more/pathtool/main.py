from __future__ import print_function

import argparse
import csv
import inspect
from dectate import Query
from dectate.tool import parse_app_class  # XXX implementation detail
from morepath.directive import ViewAction, PathAction, MountAction


def path_tool(app_class):
    """Command-line query tool for Morepath path information.

    Creates a file with information about all paths generated by a
    Morepath app, including points of definition.

    usage: morepath_paths [-h] [--app APP] filename

    param app_class: the root :class:`App` subclass to query by default.

    """
    parser = argparse.ArgumentParser(description="Query Morepath paths")
    parser.add_argument('--app', help="Dotted name for App subclass.",
                        type=parse_app_class)
    parser.add_argument('--format',
                        default='csv',
                        choices=['text', 'csv'],
                        help="Format of output. Defaults to plain csv.")
    parser.add_argument('filename')

    args, filters = parser.parse_known_args()

    if args.app:
        app_class = args.app

    infos = get_path_and_view_info(app_class)

    if args.format == 'text':
        with open(args.filename, 'w') as f:
            format_text(f, infos)
    elif args.format == 'csv':
        with open(args.filename, 'wb') as f:
            format_csv(f, infos)


def max_length(infos, name):
    return max([len(d[name]) for d in infos])


def format_text(f, infos):
    for line in format_text_helper(infos):
        f.write(line)
        f.write(u'\n')


def format_text_helper(infos):
    for info in infos:
        if 'predicates' not in info:
            predicates_s = ''
        else:
            predicates_s = ','.join(
                [u'%s=%s' % (name, value)
                 for name, value in sorted(info['predicates'].items())])
        info['predicates_s'] = predicates_s

    max_path_length = max_length(infos, 'path')
    max_predicates_s_length = max_length(infos, 'predicates_s')
    max_directive_length = max_length(infos, 'directive')

    max_path_length = max([max_path_length, max_predicates_s_length])

    t_path = (u"{path:<{max_path_length}} "
              u"{directive:<{max_directive_length}} "
              u"{filelineno}")
    t_view = (u"{predicates:<{max_path_length}} "
              u"{directive:<{max_directive_length}} "
              u"{filelineno}")
    for info in infos:
        if 'predicates' in info:
            info['predicates'] = u','.join(
                [u'%s=%s' % (name, value)
                 for name, value in sorted(info['predicates'].items())])
            yield t_view.format(
                max_path_length=max_path_length,
                max_directive_length=max_directive_length,
                **info)
        else:
            yield t_path.format(
                max_path_length=max_path_length,
                max_directive_length=max_directive_length,
                **info)


def format_csv(f, infos):
    fieldnames = [u'path', u'directive', u'filename', u'lineno',
                  u'model', u'view_name', u'request_method',
                  u'extra_predicates']
    w = csv.DictWriter(f, fieldnames=fieldnames,
                       extrasaction='ignore')
    w.writeheader()
    for info in infos:
        w.writerow(info)


def get_path_and_view_info(app_class):
    result = []
    for action, path in get_path_and_view_actions(app_class):
        directive = action.directive
        # XXX in next release of dectate can use directive.directive_name again
        directive_name = directive.configurable._action_classes[
            directive.action_factory]
        code_info = directive.code_info
        d = {'directive': directive_name,
             'filelineno': code_info.filelineno(),
             'path': path,
             'sort_path': path,
             'model': dotted_name(action.model),
             'filename': code_info.path,
             'lineno': code_info.lineno}
        if isinstance(action, ViewAction):
            d['predicates'] = action.predicates
            # this makes assumptions about core Morepath we could
            # get from configuration but we won't bother
            d['view_name'] = action.predicates.get('name', '')
            d['request_method'] = action.predicates.get('request_method',
                                                        'GET')
            if (set(action.predicates.keys()) - set(
                    ['name', 'request_method'])):
                d['extra_predicates'] = 'y'
            if action.internal:
                d['path'] = 'internal'

        result.append(d)
    return sort_path_and_view_info(result)


def directive_sort_key(directive):
    sort_after = directive not in ['path', 'mount']
    return sort_after, directive


def sort_path_and_view_info(infos):
    def key(d):
        return (
            d['sort_path'],
            directive_sort_key(d['directive']),
            d.get('view_name', ''),
            d.get('request_method', ''),
            d['filename'],
            d['lineno'])
    return sorted(infos, key=key)


def get_path_and_view_actions(app_class, base_path=''):
    model_to_view = {}
    q = Query(ViewAction)
    for action, f in q(app_class):
        model_to_view.setdefault(action.model, []).append(action)

    for action, path in get_path_actions(app_class, base_path):
        yield action, path
        if isinstance(action, MountAction):
            for sub_action, sub_path in get_path_and_view_actions(
                    action.app, path):
                yield sub_action, sub_path
            continue
        for view_action, view_path in get_view_actions(app_class, path,
                                                       model_to_view,
                                                       action.model):
            yield view_action, view_path


def get_path_actions(app_class, base_path):
    q = Query(PathAction)
    for action, f in q(app_class):
        if not isinstance(action, (PathAction, MountAction)):
            continue
        path = u'/'.join([base_path, normalize_path(action.path)])
        if action.absorb:
            path += '/...'
        yield action, path


def get_view_actions(app_class, base_path, model_to_view, model):
    view_actions = []
    for class_ in inspect.getmro(model):
        view_actions.extend(model_to_view.get(class_, []))
    for view_action in view_actions:
        name = view_action.predicates.get('name', u'')
        path = base_path
        if name:
            path = path + u'/+' + name
        yield view_action, path


def normalize_path(path):
    if path.startswith('/'):
        path = path[1:]
    if path.endswith('/'):
        path = path[:-1]
    return path


def dotted_name(cls):
    return cls.__module__ + '.' + cls.__name__
