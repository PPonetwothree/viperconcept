// Module K — engineering documentation viewer (renders /documentation/*.md).
import { api } from '../core/api.js';
import { clear, h } from '../core/util.js';
import { renderMarkdown } from '../components/markdown.js';
import { errorToast } from '../components/ui.js';

export function docsView() {
  return {
    async mount(root, param) {
      const list = h('div', { class: 'list' });
      const toc = h('div', { class: 'list' });
      const content = h('div', { class: 'md' });
      root.append(h('div', { class: 'page' }, h('div', { style: { display: 'grid', gridTemplateColumns: '260px 1fr', gap: '12px', alignItems: 'start' } },
        h('div', { class: 'col', style: { position: 'sticky', top: 0 } },
          h('section', { class: 'panel' }, h('header', {}, h('h3', {}, 'Documents')), list),
          h('section', { class: 'panel scroll', style: { maxHeight: '55vh' } }, h('header', {}, h('h3', {}, 'Contents')), toc)),
        h('section', { class: 'panel body' }, content))));
      let docs;
      try { docs = await api.docs(); } catch (e) { errorToast(e); return; }
      const name = docs.includes(param) ? param : docs.includes('system_architecture.md') ? 'system_architecture.md' : docs[0];
      for (const d of docs) list.append(h('a', { class: `item ${d === name ? 'sel' : ''}`, href: `#/docs/${d}`, style: { textDecoration: 'none', color: 'inherit' } }, d.replace('.md', '').replace(/_/g, ' ')));
      try {
        content.innerHTML = renderMarkdown(await api.doc(name));
        clear(toc);
        content.querySelectorAll('h2, h3').forEach((hd) => toc.append(h('div', { class: 'item small', style: { paddingLeft: hd.tagName === 'H3' ? '20px' : '9px' }, onclick: () => hd.scrollIntoView({ behavior: 'smooth' }) }, hd.textContent)));
      } catch (e) { errorToast(e); }
    },
    unmount() {},
  };
}
