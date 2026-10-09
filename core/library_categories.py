"""Separate organization metadata; loading never writes definition files."""
import json
from core.project import write_json


class LibraryCategories:
    def load_categories(self):
        self.categories=set();self.entry_categories={}
        path=self.directory/'categories.json'
        if path.exists():
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if data.get('schema')!='amcad.library.categories':raise ValueError('Invalid category metadata')
                self.categories={self.category_path(p) for p in data['categories']}
                self.entry_categories={k:self.category_path(v) for k,v in data['entries'].items()}
            except (ValueError,TypeError,KeyError,OSError) as error:self.errors.append(f'categories.json: {error}')

    @staticmethod
    def category_path(value):
        if not isinstance(value,str):raise ValueError('Category must be text')
        parts=[p.strip() for p in value.split('/')]
        if not all(parts) or any(p in ('.','..') for p in parts):raise ValueError('Use nonempty category names separated by /')
        return '/'.join(parts)

    def category_for(self,entry):
        return self.entry_categories.get(entry.id,getattr(entry,'category','Uncategorized'))

    def save_categories(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        write_json(self.directory/'categories.json',{'schema':'amcad.library.categories','categories':sorted(self.categories),'entries':self.entry_categories})

    def create_category(self,path):
        self.categories.add(self.category_path(path));self.save_categories()

    def move_entry(self,entry_id,path):
        if entry_id not in self.definitions:raise ValueError('Unknown library entry')
        path=self.category_path(path);self.categories.add(path);self.entry_categories[entry_id]=path;self.save_categories()

    def rename_category(self,old,new):
        old=self.category_path(old);new=self.category_path(new)
        if new.startswith(old+'/'):raise ValueError('Cannot move a category into itself')
        def rename(path):return new+path[len(old):] if path==old or path.startswith(old+'/') else path
        # Capture fallback categories without rewriting component or cavity definitions.
        for entry in self.definitions.values():self.entry_categories[entry.id]=rename(self.category_for(entry))
        self.categories={rename(p) for p in self.categories};self.categories.add(new);self.save_categories()
