import sublime_plugin
import sublime
import os
import subprocess
import json
import re

class TailwindCompletions(sublime_plugin.EventListener):
    instances = {}

    def get_completions(self, view, folder):
        self.instances[folder] = {}

        tw = self.find_file(
            folder,
            ['tailwind.js', 'tailwind.config.js', 'tailwind-config.js', '.tailwindrc.js'],
            exclude_dirs = ['node_modules']
        )
        tw_plugin = self.find_node_module(folder, 'tailwindcss')

        if tw is not None and tw_plugin is not None:
            try:
                packages = sublime.packages_path()
                script = os.path.join(packages, 'sublime-tailwindcss', 'dist', 'bundle.js')
                process = subprocess.Popen([view.settings().get('node_path', 'node'), script, '-config', tw, '-plugin', tw_plugin], stdout=subprocess.PIPE)
                output = process.communicate()[0]
                path = output.decode('utf-8').splitlines()[-1]
                class_names = json.loads(path)

                self.instances[folder]['separator'] = class_names.get('separator')
                self.instances[folder]['class_names'] = class_names.get('classNames')
                self.instances[folder]['screens'] = class_names.get('screens')
                self.instances[folder]['items'] = self.get_items_from_class_names(class_names.get('classNames'), class_names.get('screens'))
                self.instances[folder]['config'] = class_names.get('config')
                self.instances[folder]['config_items'] = self.get_config_items(class_names.get('config'))
            except (FileNotFoundError, IndexError):
                pass

    def get_items_from_class_names(self, class_names, screens, keys = []):
        if class_names is None:
            return []

        items = []
        for class_name in list(class_names):
            styles = class_names.get(class_name)
            if isinstance(styles, str):
                for k in keys:
                    styles = re.sub(':%s \{(.*?)\}' % k, r'\1', styles)
                items = items + [('%s \t%s' % (class_name, styles), class_name)]
            elif screens.get(class_name) is not None:
                items = items + [('%s: \t@media (min-width: %s)' % (class_name, screens.get(class_name)), class_name + ':')]
            else:
                items = items + [('%s:' % class_name, class_name + ':')]
        return items

    def get_config_items(self, config):
        items = []
        exclude = ['modules', 'options', 'plugins']
        for key in list(config):
            value = config.get(key)
            if isinstance(value, str):
                items = items + [('%s \t%s' % (key, value), key)]
            elif isinstance(value, list) and key not in exclude:
                items = items + [('%s \t%s' % (key, ', '.join(value)), key)]
            elif key not in exclude:
                items = items + [(key, key + '.')]

        return items

    # there’s a default snippet in sublime that prints a semi-colon when
    # you type a colon within a CSS rule. e.g. "color:_" -> "color:_;"
    # we override this if we are inside an @apply
    def on_text_command(self, view, command_name, args):
        cursor = view.sel()[0].begin()
        isCss = view.match_selector(cursor, 'source.css meta.property-list.css')

        if isCss == False:
            return None

        if command_name == 'insert_snippet' and args.get('contents') == ':$0;':
            LIMIT = 250
            start = max(0, cursor - LIMIT)
            line = view.substr(sublime.Region(start, cursor))
            match = re.match('.*?@apply ([^;}]*)$', line, re.DOTALL | re.IGNORECASE)

            if match is None:
                return None

            return ('insert', { 'characters': ':' })
        else:
            return None

    def on_activated_async(self, view):
        if view.window() is None:
            return
        for folder in view.window().folders():
            if view.file_name() is not None and view.file_name().startswith(os.path.abspath(folder) + os.sep):
                if folder in self.instances:
                    break
                else:
                    self.get_completions(view, folder)
                    break

    def on_query_completions(self, view, prefix, locations):
        items = None
        class_names = None
        screens = None

        for folder in self.instances:
            if view.file_name() is not None and view.file_name().startswith(os.path.abspath(folder) + os.sep):
                items = self.instances[folder]['items']
                config_items = self.instances[folder]['config_items']
                config = self.instances[folder]['config']
                class_names = self.instances[folder]['class_names']
                screens = self.instances[folder]['screens']
                break
        if items is None:
            return []

        isCss = view.match_selector(locations[0], 'source.css meta.property-list.css')
        isHtml = view.match_selector(locations[0], 'text.html string.quoted') or view.match_selector(locations[0], 'string.quoted.jsx')

        if isCss == False and isHtml == False:
            return []

        LIMIT = 250
        cursor = locations[0] # - len(prefix) - 1
        start = max(0, cursor - LIMIT)
        line = view.substr(sublime.Region(start, cursor))

        if isCss:
            match = re.match('.*?@apply ([^;}]*)$', line, re.DOTALL | re.IGNORECASE)
        elif isHtml:
            match = re.search('\\bclass(Name)?=["\']([^"\']*)$', line, re.IGNORECASE)

        if match is not None:
            parts = match.group(len(match.groups())).split(' ')
            string = parts[-1]
            if string.startswith('.'):
                string = string[1:]
            keys = re.findall('(.*?):', string)

            if keys is None:
                return items
            else:
                return self.get_items_from_class_names(self.safeget(class_names, keys), screens, keys)
        elif isCss:
            match = re.search('config\(["\']([^\'"]*)$', line, re.IGNORECASE)
            if match is None:
                return []
            keys = match.group(1).split('.')
            if len(keys) == 1:
                return config_items
            else:
                subset = self.safeget(config, keys[:-1])
                if subset is None or not isinstance(subset, dict):
                    return []
                return self.get_config_items(subset)
        else:
            return []

    def safeget(self, dct, keys):
        for key in keys:
            try:
                dct = dct[key]
            except KeyError:
                return None
        return dct

    def find_file(self, dir, names, exclude_dirs = None):
        file = None
        for root, dirs, files in os.walk(dir):
            if exclude_dirs is not None:
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for filename in files:
                if filename in names:
                    file = os.path.join(root, filename)
                    break
            if file is not None:
                break
        return file

    def find_node_module(self, dir, name):
        module = None
        for root, dirs, files in os.walk(dir):
            if 'node_modules' not in root or name not in root:
                continue
            for filename in files:
                if filename != 'package.json':
                    continue
                basename = os.path.split(os.path.join(root, filename))[0]
                if basename.endswith(os.path.join('node_modules', name)):
                    module = basename
                    break
            if module is not None:
                break
        return module
