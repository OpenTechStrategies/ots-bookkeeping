import os
import re

from util import rm_file, run_command

VERBOSE=False

class FDF():
    def add(self, field, value):
        self.fdf += "<</T(%s)/V(%s)>>\n" % (field,value)        
    def end(self):
        """Call this to end an FDF doc and add footer material"""
        self.fdf += "] >> >>\nendobj\ntrailer\n<</Root 1 0 R>>\n%%EOF\n"
    def start(self):
        """Call this to start an FDF doc"""
        self.fdf = "%FDF-1.2\n1 0 obj<</FDF<< /Fields[\n"
    def write(self, fname):
        """Write FDF form data to file"""
        with open(fname, 'w') as fh:
            fh.write(self.fdf)

class IRSForm():
    def get_text_fields(self, fname=None):
        """Use pdftk to get form fields of type text from pdf file FNAME.  Returns a list of the names of such fields"""

        if not fname:
            fname = self.fname
            
        names = []
        fields = run_command("pdftk %s dump_data_fields" % fname).split("---")
        for field in fields:
            field = field.strip()
            lines = field.strip().split("\n")
            if lines[0].endswith("Text"):
                names.append(lines[1].split(' ')[1])
        return names

class F1099(IRSForm):
    """Class for managing 1099 forms"""
    def __init__(self, year, name, w9, fname=None):
        """YEAR is an integer with the tax year in it.

        NAME is string containing a contractor's full name, including spaces (not underscores)

        W9 is an object of class W9

        FNAME is the filename of a blank 1099 form"""
        self.year = year
        self.w9 = w9
        self.payee = name
        self.payee_ = name.replace(" ", "_")
        self.income = None#self.get_nonemployee_income()
        if os.path.exists(fname):
            self.fname = fname
        else:
            alt_fname = os.path.join(os.path.split(os.path.realpath(__file__))[0], fname)
            if os.path.exists(alt_fname):
                self.fname = alt_fname
        self.fdf = FDF()
        
        d,f=os.path.split(self.fname)
        self.fdf.fname = os.path.join(d, "%s-%s.fdf" % (self.payee_, os.path.splitext(f)[0]))
        self.out_fname = os.path.join(d, "%s-%s" % (self.payee_, f))
        self.contractor_fname = "%s-%s-contractor.pdf" % (self.payee_, os.path.splitext(f)[0])
        IRSForm.__init__(self)

    def fdf2pdf(self):
        # Make sure we have fdf data
        if not os.path.exists(self.fdf.fname):
            self.write(fdf)
            
        ## Fill out pdf form
        cmd = "pdftk %s fill_form %s output %s" % (self.fname, self.fdf.fname, self.out_fname)
        run_command(cmd)
        rm_file(self.fdf.fname)
        
    def split(self):
        """A 1099 is a series of near-identical forms sent to permutations of
        (fed, state) by (hiring party, contractor).  All these forms
        are bundled into one doc, but we need them separated so we can
        send them to the various parties electronically.  This method
        splits the 1099 PDF into PDFs that each contain just the docs
        for IRS, state, and contractor.  It deletes the filled-out PDF
        that is a combo of all the forms.

        """
        
        ## Burst and then delete original filled-out pdf
        run_command("pdftk %s burst" % (self.out_fname))
        rm_file(self.out_fname)

        #run_command("convert -quality 100 -flatten -density 150 -sharpen 0x1.0 pg_0004.pdf pg_0004.jpg")
        #run_command("convert -quality 100 -flatten -density 150 -sharpen 0x1.0 pg_0004.jpg pg_0004.pdf")
        #run_command("pdfjam --paper 'letterpaper' --offset '0 -5.5in' --outfile pg_0004-shifted.pdf pg_0004.pdf")
        run_command("pdftk pg_0004.pdf output pg_0004-flat.pdf flatten")
        run_command("pdfjam --paper 'letterpaper' --offset '0 -5.5in' --outfile pg_0004-shifted.pdf pg_0004-flat.pdf")
        d, stub = os.path.split(os.path.splitext(self.fname)[0])
        run_command("pdftk pg_0004-shifted.pdf pg_0006.pdf output %s" % (self.contractor_fname))
        rm_file("pg_0001.pdf")
        os.rename("pg_0002.pdf", "%s-%s-IRS.pdf" % (self.payee_, stub))
        os.rename("pg_0003.pdf", "%s-%s-state.pdf" % (self.payee_, stub))
        rm_file("pg_0004.pdf")
        rm_file("pg_0004-flat.pdf")
        rm_file("pg_0004-shifted.pdf")
        rm_file("pg_0005.pdf")
        rm_file("pg_0006.pdf")
        os.rename("pg_0007.pdf", "%s-%s-ots.pdf" % (self.payee_, stub))
        rm_file("pg_0008.pdf")
        
    def write_fdf(self):
            
        # Prepare to fill out pdf form fields
        form_fields = self.get_text_fields()
        filled = [
            "0",
            "Open Tech Strategies, LLC\n333 East 102nd Street, #409\nNew York, NY 10029",
            "27-3485318",
            self.w9.taxpayer_id,
            self.w9.name,
            self.w9.address1,
            self.w9.address2,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            self.income.amount,
            "",
            "",
            "",
            "",
            "", # golden parachute
            "", # Gross proceeds to atty
            "", # 409a defer
            "", # 409a income
            "", # state tax withheld
            "", # state tax withheld
            "", # state payer state/no
            "", # state payer state/no
            "", # state income
            "", # state income
        ]
        self.fdf.start()
        for f in form_fields:
            try:
                v = filled[int(re.findall("\d+", f.split("_")[-1])[0])]
            except IndexError:
                v = f.split(".")[-1]
            self.fdf.add(f,v)
        self.fdf.end()
        
        ## Write out FDF form data
        with open(self.fdf.fname, 'w') as fh:
            fh.write(self.fdf.fdf)
        
class W9(IRSForm):
    def __init__(self, name, address1, address2, taxpayer_id):
        self.name = name
        self.name_ = name.replace(" ", "_")
        self.address1=address1
        self.address2=address2
        self.taxpayer_id = taxpayer_id
        IRSForm.__init__(self)
        
    def get_name_address(self):
        """Return a string with the name and address with line breaks suitable
        for putting on an envelope."""
        return "\n".join([self.name, self.address1, self.address2])

