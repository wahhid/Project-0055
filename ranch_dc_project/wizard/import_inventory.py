
from openerp import fields, models, exceptions, api, _
import base64
import csv
import cStringIO

import logging

_logger = logging.getLogger(__name__)


class ImportInventory(models.TransientModel):
    _name = 'import.inventory'
    _description = 'Import inventory'

    @api.one
    def _find_bin(self, code):
        gondola_obj = self.env['gondola']
        args = [('code','=', code)]
        gondola = gondola_obj.search(args, limit=1)
        return gondola

    data = fields.Binary('File', required=True)
    name = fields.Char('Filename', readonly=True)
    delimeter = fields.Char('Delimeter', default=';', help='Default delimeter is ","')
    location = fields.Many2one('stock.location', 'Default Location', required=True)

    @api.one
    def action_import(self):
        """Load Inventory data from the CSV file."""
        _logger.info("Import Starting")
        ctx = self._context
        stock_inventory_periode_obj = self.env['stock.inventory.periode']
        if 'active_id' in ctx:
            periode = stock_inventory_periode_obj.browse(ctx['active_id'])
        if not self.data:
            raise exceptions.Warning(_("You need to select a file!"))

        # Decode the file data
        data = base64.b64decode(self.data)
        file_input = cStringIO.StringIO(data)
        file_input.seek(0)
        if self.delimeter:
            delimeter = str(self.delimeter)
        else:
            delimeter = ','
        reader = csv.reader(file_input, delimiter=delimeter,lineterminator='\r\n')

        #Delete All Data
        strssql = """DELETE FROM stock_inventory_source WHERE stock_inventory_periode_id={}""".format(periode.id)
        self.env.cr.execute(strssql)

        #Import All Data
        for row in reader:
            _logger.info(row)
            gondola = self._find_bin(str(row[5]))
            if not gondola:
                gondola_id = gondola.id
            else:
                gondola_id = 'NULL'
            strSQL = """INSERT INTO stock_inventory_source (
                        stock_inventory_periode_id, 
                        site,
                        warehouse, 
                        kode_pid, 
                        storagetype,
                        itemno,
                        storagebin,
                        quantno,
                        storageloc,  
                        article_id,
                        description,
                        batchno,
                        stkcat,
                        specialstock,
                        quantedqty,
                        quanteduom,
                        stocksap,                      
                        sequence, 
                        product_theoretical_qty, 
                        inventory_value) 
                        VALUES ({},'{}','{}',{},'{}',{},'{}','{}','{}','{}','{}','{}','{}','{}',{},'{}',{},{},{},{})
                     """.format(periode.id,
                                str(row[6]), #site
                                str(row[0]), #warehouse
                                int(row[1]), #kode_pid
                                str(row[2]), #storagetype
                                int(row[3]), #itemno
                                str(row[4]), #storagebin
                                str(row[5]), #quantno
                                str(row[7]), #storageloc
                                str(row[8]), #articel_id
                                str(row[9]), #description
                                str(row[10]), #batchno
                                str(row[11]), #stkcat
                                str(row[12]), #specialstock
                                float(str(row[15]).replace(',','.')), #quantedqty
                                str(row[14]), #quanteduom
                                0, #stocksap
                                0, #sequence
                                float(str(row[15]).replace(',','.')),       #product_theoretical_qty                                
                                0         #inventory_value
                                )
            self.env.cr.execute(strSQL)

