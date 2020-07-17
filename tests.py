import sys
import logging
import inspect
import unittest
from bsmdoc import BDoc


def log_info(msg):
    log = logging.getLogger("bsmdoc.test")
    log.debug(msg)


def _T(text, nl=True):
    if nl:
        return inspect.cleandoc(text) + '\n'
    return inspect.cleandoc(text)


class TestBsmdoc(unittest.TestCase):
    def run_test(self, src, out):
        doc = BDoc()
        result = doc.parse_string(src)
        self.assertEqual(result, out)

    def test_helloworld(self):
        output = '<h1>hello world</h1>\n'
        doc = BDoc()
        result = doc.parse('./docs/helloworld.bsmdoc')
        self.assertEqual(result, output)

    def test_newfun(self):
        text = r'''\newfun{bsmdoc|bsmdoc}
                   \bsmdoc
                '''
        self.run_test(_T(text), '<p>bsmdoc</p>\n')

    def test_alias(self):
        text = r'''\alias{bsmdoc|bsmdoc}
                   \alias{bsmdoc}'''
        self.run_test(_T(text), '<p>bsmdoc</p>\n')

    def test_tag(self):
        text = r'''\tag{b|bsmdoc}'''
        self.run_test(_T(text), '<p><b>bsmdoc</b></p>\n')

        text = r'''\div{myclass|bsmdoc}'''
        output = r'''
                  <p><div class="myclass">
                  bsmdoc
                  </div></p>
                  '''
        self.run_test(_T(text), _T(output))

    def test_image(self):
        text = r'''\image{bsmdoc.png}'''
        output = '<p><img src="bsmdoc.png" alt="bsmdoc.png"></p>\n'
        self.run_test(_T(text), output)

        text = r'''
                \config{image_numbering|True}
                {!image||
                    \caption{awesome figure}
                    \label{img-awesome}
                    bsmdoc.png
                !}'''
        output = r'''<figure id="img-awesome" class="figure">
                     <img src="bsmdoc.png" alt="bsmdoc.png">
                     <figcaption class="caption"><span class="tag">Fig.1.</span> awesome figure</figcaption>
                     </figure>'''

        self.run_test(_T(text), _T(output))

    def test_highlight(self):
        text = r"""{!highlight|C++|linenos=table|hl_lines=(6,)||{%
                   #include <iostream>
                   using namespace std;

                   int main ()
                   {
                       cout << "Hello World!";
                       return 0;
                   }
                   %}!}"""
        output = r'''
                  <table class="syntaxtable"><tr><td class="linenos"><div class="linenodiv"><pre>1
                  2
                  3
                  4
                  5
                  6
                  7
                  8</pre></div></td><td class="code"><div class="syntax"><pre><span></span><span class="cp">#include</span> <span class="cpf">&lt;iostream&gt;</span><span class="cp"></span>
                  <span class="k">using</span> <span class="k">namespace</span> <span class="n">std</span><span class="p">;</span>

                  <span class="kt">int</span> <span class="nf">main</span> <span class="p">()</span>
                  <span class="p">{</span>
                  <span class="hll">    <span class="n">cout</span> <span class="o">&lt;&lt;</span> <span class="s">&quot;Hello World!&quot;</span><span class="p">;</span>
                  </span>    <span class="k">return</span> <span class="mi">0</span><span class="p">;</span>
                  <span class="p">}</span>
                  </pre></div>
                  </td></tr></table>
                  '''
        self.run_test(_T(text), _T(output, False))

    def test_heading(self):
        text = r'''
                = heading 1
                == heading 2
                === heading 3
                ==== heading 4
                ===== heading 5
                ====== heading 6
                '''
        output = r'''
                  <h1>heading 1</h1>
                  <h2>heading 2</h2>
                  <h3>heading 3</h3>
                  <h4>heading 4</h4>
                  <h5>heading 5</h5>
                  <h6>heading 6</h6>
                  '''
        self.run_test(_T(text), _T(output))

        text = r'''
                \config{heading_numbering|True}
                = heading 1
                == heading 2
                === heading 3
                ==== heading 4
                ===== heading 5
                ====== heading 6
                '''
        output = r'''
                  <h1 id="sec-1">1 heading 1</h1>
                  <h2 id="sec-1-1">1.1 heading 2</h2>
                  <h3 id="sec-1-1-1">1.1.1 heading 3</h3>
                  <h4 id="sec-1-1-1-1">1.1.1.1 heading 4</h4>
                  <h5 id="sec-1-1-1-1-1">1.1.1.1.1 heading 5</h5>
                  <h6 id="sec-1-1-1-1-1-1">1.1.1.1.1.1 heading 6</h6>
                  '''
        self.run_test(_T(text), _T(output))

    def test_video(self):
        text = r'''\video{bsmdoc.mp4}'''
        output = r'''
                  <p><div class="video">
                  <video controls><source src="bsmdoc.mp4">
                  Your browser does not support the video tag.</video>
                  </div></p>
                  '''
        self.run_test(_T(text), _T(output))

        text = r'''
                \config{image_numbering|True}
                {!video||
                \caption{awesome video}
                \label{video-awesome}
                 bsmdoc.mp4
                !}'''

        output = r'''
                  <div id="video-awesome" class="video">
                  <video controls><source src=" bsmdoc.mp4">
                  Your browser does not support the video tag.</video>
                  <div class="caption">
                  <span class="tag">Fig.1.</span> awesome video
                  </div>
                  </div>
                  '''

        self.run_test(_T(text), _T(output))

    def test_table(self):
        text = r'''
                {{
                 option | description ||+
                 item 1 | description 1 ||-
                 item 2 | description 2 ||-
                }}'''
        output = r'''
                  <table>
                  <thead>
                  <tr>
                  <th>option</th><th>description</th>
                  </tr>
                  </thead>
                  <tbody>
                  <tr>
                  <td>item 1</td><td>description 1</td>
                  </tr>
                  <tr>
                  <td>item 2</td><td>description 2</td>
                  </tr>
                  </tbody>
                  </table>
                  '''
        self.run_test(_T(text), _T(output))

    def test_list(self):
        text = r'''
                - item 1
                -- item 2
                - item 3

                * item 1
                ** item 1.1
                ** item 1.2

                - item 1
                -* item 1.1
                '''
        output = r'''
                  <ul>
                  <li>item 1
                  <ul>
                  <li>item 2</li>
                  </ul></li>
                  <li>item 3</li>
                  </ul>
                  <ol>
                  <li>item 1
                  <ol>
                  <li>item 1.1</li>
                  <li>item 1.2</li>
                  </ol></li>
                  </ol>
                  <ul>
                  <li>item 1
                  <ol>
                  <li>item 1.1</li>
                  </ol></li>
                  </ul>
                  '''
        self.run_test(_T(text), _T(output))

    def test_equation(self):
        text = r'''$f=ma$'''
        output = r'''$f=ma$'''

        self.run_test(text, output)

        text = r'''
                {!math||{%
                    \begin{align}
                    \begin{bmatrix}
                    0      & \cdots & 0      \\
                    \vdots & \ddots & \vdots \\
                    0      & \cdots & 0
                    \label{eqn:matrix}
                    \end{bmatrix}
                    \end{align}
                %}!}
                '''
        output = r'''
                  <div class="mathjax">
                  $$
                  \begin{align}
                  \begin{bmatrix}
                  0      & \cdots & 0      \\
                  \vdots & \ddots & \vdots \\
                  0      & \cdots & 0
                  \label{eqn:matrix}
                  \end{bmatrix}
                  \end{align}
                  $$
                  </div>
                  '''

        self.run_test(_T(text), _T(output))


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr)
    logging.getLogger("bsmdoc.test").setLevel(logging.DEBUG)
    unittest.main()
