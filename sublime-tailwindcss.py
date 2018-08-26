import sublime_plugin
import sublime
import os
import subprocess
import json
import re

class TailwindCompletions(sublime_plugin.EventListener):
    activated = False

    def get_completions(self):
        folders = sublime.active_window().folders()

        if len(folders) == 0:
            self.activated = False
            return

        tw = self.find_file(
            folders[0],
            ['tailwind.js', 'tailwind.config.js', 'tailwind-config.js', '.tailwindrc.js'],
            exclude_dirs = ['node_modules']
        )
        tw_plugin = self.find_node_module(folders[0], 'tailwindcss')

        if tw is not None and tw_plugin is not None:
            try:
                packages = sublime.packages_path()
                script = os.path.join(packages, 'sublime-tailwindcss', 'dist', 'bundle.js')
                process = subprocess.Popen(['node', script, '-config', tw, '-plugin', tw_plugin], stdout=subprocess.PIPE)
                output = process.communicate()[0]
                path = output.decode('utf-8').splitlines()[0]
                class_names = json.loads(path)
                self.separator = class_names.get('separator')
                self.class_names = class_names.get('classNames')
                self.screens = class_names.get('screens')
                self.items = self.get_items_from_class_names(self.class_names)
                return self.items
            except FileNotFoundError:
                self.activated = False
            except IndexError:
                return []

    def get_items_from_class_names(self, class_names, keys = []):
        if class_names is None:
            return []

        items = []
        for class_name in list(class_names):
            styles = class_names.get(class_name)
            if isinstance(styles, str):
                for k in keys:
                    styles = re.sub(':%s \{(.*?)\}' % k, r'\1', styles)
                items = items + [('%s \t%s' % (class_name, styles), class_name)]
            elif self.screens.get(class_name) is not None:
                items = items + [('%s: \t@media (min-width: %s)' % (class_name, self.screens.get(class_name)), class_name + ':')]
            else:
                items = items + [('%s:' % class_name, class_name + ':')]
        return items

    # there’s a default snippet in sublime that prints a semi-colon when
    # you type a colon within a CSS rule. e.g. "color:_" -> "color:_;"
    # we override this if we are inside an @apply
    def on_text_command(self, view, command_name, args):
        # if command_name == 'insert' and args.get('characters') == ':':
        #     view.run_command('hide_auto_complete', [])
        #     return None
        cursor = view.sel()[0].begin()
        isCss = view.match_selector(cursor, 'source.css meta.property-list.css')

        if isCss == False:
            return None

        if command_name == 'insert_snippet' and args.get('contents') == ':$0;':
            # print('wat')
            # word_separators = view.settings().get("word_separators")
            # view.settings().set("word_separators", "")
            # sublime.set_timeout(lambda: view.settings().set("word_separators", word_separators), 0)

            # view.settings().set( "auto_complete_triggers",  )
            LIMIT = 250
            start = max(0, cursor - LIMIT)
            line = view.substr(sublime.Region(start, cursor))
            match = re.match('.*?@apply ([^;}]*)$', line, re.DOTALL | re.IGNORECASE)

            if match is None:
                return None

            return ('insert', { 'characters': ':' })
        else:
            return None

    # def on_post_text_command(self, view, command_name, args):
    #     print(command_name)
    #     if command_name == 'insert' and args.get('characters') == ':':
    #         # view.run_command('hide_auto_complete', [])

    #         view.run_command('auto_complete', [])

    def on_activated_async(self, view):
        if self.activated is False:
            self.activated = True
            self.get_completions()

    def on_query_completions(self, view, prefix, locations):
        if not hasattr(self, 'items'):
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

        if match is None:
            return []
        # if hasattr(self, 'items'):
        #     print('dd')
        # else:
        #     triggers = view.settings().get("auto_complete_triggers")
        #     print(triggers)
        #     view.settings().set("auto_complete_triggers", [{"selector": "source.css", "characters": ":"}])
        # sublime.set_timeout(lambda: view.settings().set("auto_complete_triggers", word_separators), 0)
        # view.settings().set( "auto_complete_triggers", [{"selector": "source.css meta.property-name.css", "characters": ":"}] )

        # word_separators = view.settings().get("word_separators")
        # view.settings().set("word_separators", "")
        # sublime.set_timeout(lambda: view.settings().set("word_separators", word_separators), 0)

        parts = match.group(len(match.groups())).split(' ')
        string = parts[-1]
        if string.startswith('.'):
            string = string[1:]
        keys = re.findall('(.*?):', string)

        if keys is None:
            return self.items
        else:
            # return [("%s" % class_name, class_name) for class_name in list(self.safeget(self.class_names, keys))]
            return self.get_items_from_class_names(self.safeget(self.class_names, keys), keys)

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
