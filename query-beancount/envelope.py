import os

from util import run_command

class Envelope():
    """This is a generic class for addressing envelopes and adding
    addresses to the right place on a page for windowed envelopes.  Wrap
    it or subclass it as you please."""
    def __init__(self,
                 name_address,
                 ret_address=""):
        """CONTRACTOR is an object of class Contractor"""
        self.name_address = name_address
        self.ret_address = ret_address

    def tex_text(self, text):
        """Texify a string"""
        return text.replace("\n",r"\\").replace("#",r"\#")
    
    def get_envelope_tex(self, address=None, ret_address=None):
        """ADDRESS is a multiline string we'll print as the name/address

        Returns a string containing tex for an envelope we can print on."""
        if address == None:
            address = self.name_address
        if ret_address == None:
            ret_address=self.ret_address
        ret = r"""% envelope.tex
\documentclass{letter}
\usepackage[left=1in,top=0.5in,papersize={4.125in,9.5in},landscape,twoside=false]{geometry}
\setlength\parskip{0pt}
\pagestyle{empty}

\begin{document}"""
        ret += "\n\n" + self.tex_text(ret_address) + "\n\n"
        ret += r"""\vspace{1.1in}\large
\setlength\parindent{3.7in}\begin{minipage}[t]{0.5\textwidth}
"""
        ret += self.tex_text(address)
        ret += "\n\end{minipage}\n\end{document}"
        return ret

    def get_address_tex(self, address=None, ret_address=None):
        if address == None:
            address = self.name_address
        if ret_address == None:
            ret_address=self.ret_address
        ret = r"""% envelope.tex
\documentclass{letter}[12pt]
\usepackage[left=0.5in,top=0.5in,]{geometry}
\usepackage[absolute]{textpos}
\setlength\parskip{0pt}
\pagestyle{empty}

\begin{document}"""
        ret += self.textblock(2,1,self.tex_text(ret_address))
        ret += self.textblock(2,3.25,self.tex_text(address))
        ret += r"\end{document}"
        return ret
    def make_address_stamp(self, fname):
        """Write a pdf that is a blank page except for an address at the
        bottom of the page suitable for display in a windowed envelope.

        FNAME is a string to which we'll write the pdf.

        We're using Staples No. 10 gummed envelopes White Wove 24lb.
        Model number appears to be 50151.  These have no return
        address window.  If we end up supporting multiple envelopes,
        each with the window in a different position, we can add
        parameters to select.

        """
        self.make_pdf(self.get_address_tex(ret_address=""), fname)
    def make_envelope_pdf(self, fname):
        self.make_pdf(self.get_envelope_tex(), fname)
    def make_pdf(self, tex, fname):
        """Write a pdf that can be printed to print address information on an
        envelope.  Don't use this for windowed envelopes.  For those,
        you want to add the address to the document that goes in the
        envelope.

        FNAME is a string to which we'll write the pdf.

        """
        
        tex_fname = os.path.splitext(fname)[0]+'.tex'
        with open(tex_fname, 'w') as fh:
            fh.write(tex)
        run_command("pdflatex -interaction nonstopmode -halt-on-error -file-line-error %s" % tex_fname)
        os.unlink(os.path.splitext(fname)[0]+".aux")
        os.unlink(os.path.splitext(fname)[0]+".log")
        os.unlink(os.path.splitext(fname)[0]+".tex")
    def stamp_pdf(self, stamp_pdf, input_pdf, output_pdf):
        """Overlay STAMP_PDF on INPUT_PDF and write the result to OUTPUT_PDF"""

        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            orig_dir = os.getcwd()
            os.chdir(temp_dir)
            run_command("cp %s ." % os.path.join(orig_dir, stamp_pdf))
            run_command("cp %s ." % os.path.join(orig_dir, input_pdf))
            run_command("pdftk %s burst" % input_pdf)
            run_command("mv pg_0001.pdf stamp_me.pdf")
            run_command("pdftk stamp_me.pdf stamp %s output pg_0001.pdf" % (stamp_pdf))
            run_command("pdftk pg_0*.pdf output %s" % (os.path.join(orig_dir, output_pdf)))
            os.chdir(orig_dir)
        return
        del_orig = False
        if input_pdf == output_pdf:
            input_pdf = os.path.splitext(input_pdf)[0] + ".orig.pdf"
            run_command("cp %s %s" % (output_pdf, input_pdf))
            del_orig = True
            
        run_command("pdftk %s stamp %s output %s" % (input_pdf, stamp_pdf, output_pdf))

        if del_orig:
            run_command("rm %s" % input_pdf)
    def textblock(self, x, y, text):
        return "\n"+r"\begin{textblock}{10}(" + str(x) + "," + str(y) + ")" + text + r"\end{textblock}"+"\n"

