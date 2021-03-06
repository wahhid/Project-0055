from openerp import models, fields, api, exceptions, _
from datetime import datetime
import base64
import StringIO
import logging
import io

_logger = logging.getLogger(__name__)


class Gondola(models.Model):
    _name = 'gondola'

    stock_warehouse_id = fields.Many2one('stock.warehouse','warehouse #')
    code = fields.Char('Code', size=20, required=True)
    name = fields.Char('Name', size=100, required=True)
    state = fields.Selection([('ready','Ready'),('active','Active')], 'Status', default='ready')

    @api.model
    def create(self, vals):
        vals.update({'code': vals.get('code').upper()})
        return super(Gondola, self).create(vals)

    @api.multi
    def write(self, vals):
        if 'code' in vals.keys():
            vals.update({'code': vals.get('code').upper()})
        return super(Gondola, self).write(vals)

    _sql_constraints = [
        ('uniq_code', 'unique(code)', "A code already exists with this name . code's name must be unique!"),
    ]


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    gondola_ids = fields.One2many('gondola','stock_warehouse_id','Bins')


class StockInventoryPeriode(models.Model):
    _name = 'stock.inventory.periode'

    @api.one
    def trans_open(self):
        self.stock_inventory_trans_ids.write({'state': 'open'})
        self.write({'state':'open'})

    @api.one
    def trans_close(self):
        self.stock_inventory_trans_ids.write({'state': 'done'})
        self.write({'state': 'done'})

    @api.one
    def trans_re_open(self):
        self.stock_inventory_trans_ids.write({'state': 'open'})
        self.write({'state': 'open'})

    @api.one
    def trans_calculate(self):
        print "Trans Calculate"
        stock_inventory_trans_line_obj = self.env['stock.inventory.trans.line']
        for source in self.stock_inventory_source_ids:
            _logger.info(str(source))
            gondola_ids = self.env['gondola'].search([('code','=', source.storagebin)])
            if not gondola_ids:
                _logger.info('Gondola Not Found')
                continue
            _logger.info(gondola_ids)
            args = [
                ('stock_inventory_periode_id', '=' , self.id),
                ('gondola_id', '=', gondola_ids[0].id),
                ('article_id','=', source.article_id),
                ('batchno','=', source.batchno),]
            _logger.info('Args')   
            _logger.info(args)
            stock_inventory_trans_line_ids = stock_inventory_trans_line_obj.search(args)
            _logger.info('Trans Line IDS')
            _logger.info(stock_inventory_trans_line_ids)
            quantity = 0
            for line in stock_inventory_trans_line_ids:
                #line.stock_inventory_trans_source_id = source.id
                quantity += line.qty1
            source.product_real_qty = quantity
            #diff = source.product_real_qty - source.product_theoretical_qty
            #if diff < 0:
            #    diff = diff * -1
            #source.product_diff_qty = diff
            #if diff != 0:
            #   source.iface_diff = True
            #source.inventory_value_diff = source.inventory_value * diff

        self.iface_calculate = True
        self.datetime_calculate = datetime.now()
        
        #self.trans_generate_file()
        self.trans_generate_exception_file()

    @api.one
    def trans_next_step(self):
        for line in self.stock_inventory_trans_ids:
            line.trans_next_step()

    @api.one
    def trans_generate_exception_file(self):
        output = StringIO.StringIO()
        for periode in self:
           for trans in self.stock_inventory_trans_ids:
               for line in trans.line_ids.sorted(key=lambda r:r.gondola_id.name):
                    if not line.stock_inventory_trans_source_id:
                        content = "{};{};{};{};{};{};{}\r\n".format(
                                    periode.name,
                                    trans.gondola_id.name,
                                    line.ean,
                                    line.article_id,
                                    line.product_id.name, 
                                    line.batchno, 
                                    line.qty1)
                        _logger.info(content)
                        output.write(content)
        self.exception_csv_file = base64.encodestring(output.getvalue())


    @api.one
    def _get_sap_csv_url(self):
        self.sap_csv_url = "/csv/download/sap/{}/".format(self.id)

    @api.model
    def _sap_csv_download(self, vals):
        
        sql = """SELECT 
                     quote_nullable(site),
                     quote_nullable(warehouse),
                     quote_nullable(kode_pid),
                     quote_nullable(storagetype),
                     quote_nullable(itemno),
                     quote_nullable(storagebin),
                     quote_nullable(quantno),

                 FROM
                     stock_inventory_source
                 WHERE stock_inventory_periode_id={}""".format(vals.get('periode_id'))
        self.env.cr.execute(sql)
        rows = self.env.cr.fetchall()
        csv = ''
        if rows:
            for row in rows:
                csv_row = ""
                for item in row:
                    csv_row += "{};".format(item)
                csv += "{}\n".format(csv_row[:-1])
        return csv

    @api.multi
    def action_stock_inventory_source_tree(self):
        periode = self
        action = self.env['ir.model.data'].xmlid_to_object('ranch_dc_project.action_stock_inventory_source_tree2').read()[0]
        action['context'] = {
            'default_stock_inventory_periode_id': periode.id,
        }
        return action

    @api.multi
    def action_stock_inventory_trans_tree(self):
        periode = self
        action = self.env['ir.model.data'].xmlid_to_object('ranch_dc_project.action_stock_inventory_trans_tree2').read()[0]
        action['context'] = {
            'default_stock_inventory_periode_id': periode.id,
        }
        return action

    @api.multi
    def action_stock_inventory_trans_line_tree(self):
        periode = self
        action = self.env['ir.model.data'].xmlid_to_object('ranch_dc_project.action_stock_inventory_trans_line_tree2').read()[0]
        action['context'] = {
            'default_stock_inventory_periode_id': periode.id,
        }
        return action

    name = fields.Char('Name', size=50, required=True)
    trans_date = fields.Date('Date', index=True)
    location_id = fields.Many2one('stock.location','Location', index=True)
    sap_csv_url = fields.Char(compute='_get_csv_url')
    iface_calculate = fields.Boolean('Calculated', default=False)
    datetime_calculate = fields.Datetime('Calculate Time')
    sap_csv_filename = fields.Char('File Name', readonly=True, default="sap.csv")
    sap_csv_file = fields.Binary('SAP File', readonly=True)
    exception_csv_filename = fields.Char('Exception File Name', readonly=True, default="exception.csv")
    exception_csv_file = fields.Binary('Exception File', readonly=True)
    stock_inventory_source_ids = fields.One2many('stock.inventory.source','stock_inventory_periode_id', 'Sources')
    stock_inventory_trans_ids = fields.One2many('stock.inventory.trans','stock_inventory_periode_id', 'Transactions')
    state = fields.Selection([('draft','New'),('open','Open'),('done','Close')], 'Status', default='draft')


class StockInventorySource(models.Model):
    _name = 'stock.inventory.source'

    @api.one
    def _calculate_line_quantity(self):
        qty = 0
        for source in self:
            for line in source.line_ids:
                qty += line.qty
            self.product_real_qty = qty

    #@api.one
    #def _calculate_product_diff_qty(self):
    #    for source in self:
    #        diff = source.product_theoretical_qty - source.product_real_qty
    #        source.product_diff_qty = diff
    #        source.inventory_value_diff = diff * source.inventory_value

    stock_inventory_periode_id = fields.Many2one('stock.inventory.periode','Periode #', ondelete='cascade', index=True)
    site = fields.Char('Site', size=20, index=True)
    warehouse = fields.Char('Warehouse', size=20, index=True)
    kode_pid = fields.Integer('Kode PID', size=20, index=True)
    storagetype = fields.Char('Storage Type', size=100, index=True)
    itemno = fields.Integer('Item No', size=50, index=True)
    storagebin = fields.Char('Bin', size=50, index=True)
    quantno = fields.Char('Quant No', index=True)
    storageloc = fields.Char('Storage Loc', index=True)
    article_id = fields.Char('Article #', size=50, index=True)
    description = fields.Char('Description', size=200, index=True)
    batchno = fields.Char('Batch No', size=50, index=True)
    stkcat = fields.Char('Stk Cat', size=50, index=True)
    specialstock = fields.Char('Special Stock', size=50, index=True)
    quantedqty = fields.Float('Quanted Qty')
    quanteduom = fields.Char('Quanted Uom')
    stocksap = fields.Float('Stock SAP')
    diff = fields.Boolean('Diff', default=False, readonly=True)
    sequence = fields.Integer('Sequence')
    product_theoretical_qty = fields.Float('Theoretical Qty', digits=(12,3), default=0.000)
    product_real_qty = fields.Float("Real Qty", digits=(12,3), default=0.000)
    #product_diff_qty = fields.Float("Diff Qty", digits=(12,3), default=0.000)
    #inventory_value = fields.Float('Inventory Value', default=0.0)
    #inventory_value_diff = fields.Float('Value Diff', reaodnly=True)
    #iface_diff = fields.Boolean('Diff', readonly=True, default=False)
    line_ids = fields.One2many('stock.inventory.trans.line','stock_inventory_trans_source_id','Lines')


class StockInventoryTrans(models.Model):
    _name = 'stock.inventory.trans'
    _order = 'create_date'

    @api.multi
    def name_get(self):
        res = super(StockInventoryTrans, self).name_get()
        data = []
        for trans in self:
            display_value = trans.stock_inventory_periode_id.name
            display_value += " - "
            display_value += trans.gondola_id.name
            data.append((trans.id, display_value))
        return data

    @api.one
    def trans_read_group(self):
        #for group in self.env['sale.report'].read_group(domain, ['product_id', 'product_uom_qty'], ['product_id']):
        #    r[group['product_id'][0]] = group['product_uom_qty']

        stock_inventory_trans_line_obj = self.env['stock.inventory.trans.line']
        domain = [('stock_inventory_periode_id','=',self.stock_inventory_periode_id.id),]
        fields = ['product_id','qty']
        groupby = ['product_id']
        stock_inventory_trans_line_group= stock_inventory_trans_line_obj.read_group(domain, fields, groupby)
        for line_group in stock_inventory_trans_line_group:
            _logger.info("Line")
            _logger.info(line_group['product_id'][0] + ' - ' + line_group['qty'])

    @api.one
    def trans_next_step(self):
        trans = self
        if trans.step == '1':
            for line in trans.line_ids:
                qty = line.qty1
                line.qty2 = qty
            trans.write({'step': '2'})
        elif trans.step == '2':
            for line in trans.line_ids:
                qty = line.qty2
                line.qty3 = qty
            trans.write({'step': '3'})

    @api.model
    def process_next_step(self):
        active_ids = self._context.get('active_ids')
        for active_id in active_ids:
            trans = self.env['stock.inventory.trans'].browse(active_id)
            _logger.info(trans)
            if trans.step == '1':
                for line in trans.line_ids:
                    qty = line.qty1
                    line.qty2 = qty
                trans.write({'step': '2'})
            elif trans.step == '2':
                for line in trans.line_ids:
                    qty = line.qty2
                    line.qty3 = qty
                trans.write({'step': '3'})

    @api.one
    def trans_calculate(self):
        stock_inventory_source_obj = self.env['stock.inventory.source']
        strsql = """SELECT distinct(gondola_id, article_id, batchno) FROM stock_inventory_trans_line WHERE stock_inventory_trans_id={}""".format(self.id)
        _logger.info(strsql)
        self.env.cr.execute(strsql)
        articles = self.env.cr.fetchall()
        for article in articles:
            _logger.info(gondola_id)
            strsql = """SELECT sum(qty) FROM stock_inventory_trans_line WHERE stock_inventory_trans_id={} AND gondola_id={} AND article_id='{}' AND batchno='{}'""".format(self.id, article[0], article[1], article[2])
            _logger.info(strsql)
            self.env.cr.execute(strsql)
            quantity =  self.env.cr.fetchone()[0]
            gondola_id = self.env['gondola'].browse(article[0])
            if gondola_id:
                args = [('stock_inventory_periode_id','=', self.stock_inventory_periode_id.id),
                        ('storagebin','=', gondola_id.code),
                        ('article_id','=',article[1]),
                        ('batchno','=', article[2])]
                stock_inventory_source_ids = stock_inventory_source_obj.search(args)
                for stock_inventory_source in stock_inventory_source_ids:
                    stock_inventory_source.product_real_qty = quantity
        self.iface_calculate = True
        self.datetime_calculate = datetime.now()

    stock_inventory_periode_id = fields.Many2one('stock.inventory.periode','Periode #',  ondelete='cascade', index=True)
    gondola_id = fields.Many2one('gondola','Bin', index=True)
    user_id = fields.Many2one('res.users', 'User', index=True)
    step = fields.Selection([('1','First Collection'),('2','Second Collection'),('3','Third Collection')], 'Step', default='1', index=True)
    iface_calculate = fields.Boolean('Calculated', default=False)
    datetime_calculate = fields.Datetime('Calculate Time')
    state = fields.Selection([('open','Open'),('done','Close')], 'Status', index=True)
    line_ids = fields.One2many('stock.inventory.trans.line', 'stock_inventory_trans_id', 'Lines', ondelete="cascade")


class StockInventoryTransLine(models.Model):
    _name = 'stock.inventory.trans.line'
    _order = 'create_date'

    stock_inventory_trans_id = fields.Many2one('stock.inventory.trans','Transaction #',  ondelete='cascade', index=True)
    stock_inventory_periode_id = fields.Many2one('stock.inventory.periode', string='Periode #', related='stock_inventory_trans_id.stock_inventory_periode_id', store=True, readonly=True)
    stock_inventory_trans_source_id = fields.Many2one('stock.inventory.source', 'Source', readonly=True)
    date = fields.Datetime('Date', default=lambda self: fields.datetime.now())
    gondola_id = fields.Many2one(comodel_name='gondola', string='Bin', related='stock_inventory_trans_id.gondola_id', store=True)
    product_id = fields.Many2one('product.template','Product')
    batchno = fields.Char('Batch No', size=50, index=True)
    ean = fields.Char('Ean', related='product_id.ean')
    article_id = fields.Char('Article #', size=20)
    user_id = fields.Many2one(comodel_name='res.users', string='User', related='stock_inventory_trans_id.user_id', store=True)
    step = fields.Selection([('1','First Collection'),('2','Second Collection'),('3','Third Collection')], string='Step', related='stock_inventory_trans_id.step',default='1')
    qty1 = fields.Float('Qty 1', digits=(12,3), default=0.0)
    qty2 = fields.Float('Qty 2', digits=(12,3), default=0.0)
    qty3 = fields.Float('Qty 3', digits=(12,3), default=0.0)
    qty = fields.Float('Qty', digits=(12,3), default=0.0)




