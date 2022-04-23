import json
import logging
import werkzeug
import werkzeug.utils
import werkzeug.urls
import babel.dates
import time
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from math import ceil

from openerp import http
from openerp import tools, SUPERUSER_ID
from openerp.addons.website.models.website import slug
from openerp.http import request
from openerp.tools.translate import _
from openerp.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT as DTF, ustr
import logging

_logger = logging.getLogger(__name__)


class WebsiteWarehoue(http.Controller):

    def get_product(self, product_id):
        stock_warehouse_obj = http.request.env['product.template']

    def get_product_batch(self):
        stock_inventory_trans_source_obj = http.request.env['stock.inventory.source']
        args = [('stock_inventory_periode_id','=', request.session.periodeid),('storagebin','=', request.session.gondolacode),('article_id','=', request.session.articleid)]
        _logger.info("Batch Args")
        _logger.info(args)
        source_ids = stock_inventory_trans_source_obj.search(args)
        batchnos = []
        for source_id in source_ids:
            batchno = {}
            if source_id.batchno:
                batchno.update({'batchno': source_id.batchno})    
                batchnos.append(batchno)
        _logger.info("BatchNos")
        _logger.info(batchnos)
        return batchnos        
    
    @http.route('/csv/download/sap/<int:periode_id>/', auth='public')
    def csvdownload(self, periode_id, **kw):
        return http.request.env['stock.inventory.periode']._sap_csv_download({'periode_id': periode_id})

    @http.route('/warehouse/opname/index', type='http', auth='none', csrf=False)
    def index(self):
        request.session['islogin'] = False
        stock_warehouse_obj = http.request.env['stock.warehouse']
        datas = {}
        warehouses = stock_warehouse_obj.sudo().search([])
        datas.update({'warehouses': warehouses})
        return request.render('ranch_dc_project.warehouse_opname_index',datas)

    @http.route('/warehouse/opname/checklogin', type='http', methods=['GET','POST'], auth='public', csrf=False)
    def checklogin(self, **post):
        stock_warehouse_obj = http.request.env['stock.warehouse']
        if not request.session.uid and not post:
            return werkzeug.utils.redirect('/warehouse/opname/index', 303)
        username = post['username']
        password = post['password']
        siteid = post['siteid']              
        uid = request.session.authenticate(request.session.db, username, password)
        if uid:
            request.session['islogin'] = True
            request.session['userid'] = request.session.uid
            request.session['username'] = username
            request.session['password'] = password
            request.session['siteid']= siteid
            stock_warehouse_id = stock_warehouse_obj.sudo().browse(int(siteid))
            if stock_warehouse_id:
                request.session['warehouseid'] = stock_warehouse_id.id
                request.session['warehousename'] = stock_warehouse_id.name
            #return request.redirect('ranch_dc_project.warehouse_opname_periode_list', datas)
            #return request.redirect('warehouse/opname/periode/list')
            return werkzeug.utils.redirect('warehouse/opname/periode/list', 303)
        return werkzeug.utils.redirect('/warehouse/opname/index', 303)
        
    @http.route('/warehouse/opname/periode/list', type='http', methods=['GET','POST'], auth='user', csrf=False)
    def periode_list(self, redirect='/warehouse/opname/index', **post):
        stock_inventory_periode_obj = http.request.env['stock.inventory.periode']
        stock_warehouse_obj = http.request.env['stock.warehouse']
        res_users_obj = http.request.env['res.users']
        user = res_users_obj.browse(request.session.uid)
        stock_warehouse = stock_warehouse_obj.browse(int(request.session['siteid']))
        if stock_warehouse:
            request.session['warehouseid'] = stock_warehouse.id
            datas = {}
            #Find Periode
            args = [('state', '=', 'open')]
            periodes = stock_inventory_periode_obj.search(args)
            datas.update({'periodes': periodes})
            return request.render('ranch_dc_project.warehouse_opname_periode_list', datas)
        return request.render('ranch_dc_project.warehouse_opname_periode_list', datas)

    @http.route('/warehouse/opname/logout', type='http', auth='user', csrf=False)
    def logout(self, redirect='/warehouse/opname/index'):
        request.session.logout(keep_db=True)
        return werkzeug.utils.redirect('/warehouse/opname/index', 303)

    @http.route('/warehouse/opname/gondola/find', type='http', methods=['GET','POST'], auth='user' ,csrf=False)
    def gondola_find(self, redirect='/warehouse/opname/index', **post):
        datas={}
        periode_id = post['periodeid']
        stock_warehouse_obj = http.request.env['stock.warehouse']
        stock_inventory_periode_obj = http.request.env['stock.inventory.periode']
        stock_inventory_periode = stock_inventory_periode_obj.browse(int(periode_id))
        if stock_inventory_periode: 
            request.session['periodeid'] = stock_inventory_periode.id
            request.session['periodename'] = stock_inventory_periode.name
            stock_warehouse = stock_warehouse_obj.browse(request.session['warehouseid'])
            if stock_warehouse:
                gondolas = stock_warehouse.gondola_ids
                datas.update({'gondolas': gondolas})
        return request.render('ranch_dc_project.warehouse_opname_gondola_find', datas)


    @http.route('/warehouse/opname/gondola/result', type='http', methods=['POST'], auth='user', csrf=False)
    def gondola_result(self, redirect='/warehouse/opname/index', **post):
        datas = {}
        stock_inventory_trans_obj = http.request.env['stock.inventory.trans']
        gondola_obj = http.request.env['gondola']
        gondola_code = post['gondolacode']
        args = [('code','=', gondola_code.upper())]
        gondola_ids = gondola_obj.search(args)
        if len(gondola_ids) > 0:
            gondola = gondola_ids[0]
            request.session['gondolaid'] = gondola.id
            request.session['gondolacode'] = gondola.code
            request.session['gondolaname'] = gondola.name
            gondola.write({'state':'active'})
            args = [('stock_inventory_periode_id','=', request.session['periodeid']),('gondola_id','=', gondola.id)]
            stock_inventory_trans = stock_inventory_trans_obj.search(args)
            if stock_inventory_trans:
                request.session['transid'] = stock_inventory_trans.id
                request.session['step'] = stock_inventory_trans.step
            else:
                vals = {}
                vals.update({'stock_inventory_periode_id': request.session['periodeid']})
                vals.update({'gondola_id': gondola.id})
                vals.update({'user_id': request.session.userid})
                vals.update({'state': 'open'})
                res = stock_inventory_trans_obj.create(vals)
                request.session['transid'] = res.id
                request.session['step'] = res.step
            return request.render('ranch_dc_project.warehouse_opname_gondola_result', datas)
        else:
            datas.update({'msg': 'Gondola not found'})
            return request.render('ranch_dc_project.warehouse_opname_gondola_find', datas)

    @http.route('/warehouse/opname/trans/product', type='http', auth='user', csrf=False)
    def trans_product_find(self, redirect='/warehouse/opname/index'):
        datas = {}
        stock_inventory_trans_obj = http.request.env['stock.inventory.trans']
        args = [('stock_inventory_periode_id','=', request.session.periodeid),('gondola_id','=', request.session.gondolaid),]
        stock_inventory_trans = stock_inventory_trans_obj.search(args)
        if len(stock_inventory_trans.line_ids) > 0:
            stock_inventory_trans_line = stock_inventory_trans.line_ids[-1]
        else:
            stock_inventory_trans_line = False
        datas.update({'stock_inventory_trans_line': stock_inventory_trans_line})
        return request.render('ranch_dc_project.warehouse_opname_trans_product',datas)
    
    @http.route('/warehouse/opname/trans/batch', type='http', auth='user', csrf=False)
    def trans_batch_find(self, redirect='/warehouse/opname/index', **post):
        datas = {}
        ean = post['ean']
        product_template_obj = http.request.env['product.template']

        args = [('default_code', '=', str(ean))]
        product_template = product_template_obj.search(args)
        if not product_template:
            args = [('article_id','=', str(ean))]
            product_template = product_template_obj.search(args)
            if not product_template:
                datas.update({'msg': 'Product or Article not found'})
                return request.render('ranch_dc_project.warehouse_opname_trans_product', datas)     
        
        request.session['ean'] = ean
        request.session['productid'] = product_template[0].id
        request.session['productname'] = product_template[0].name
        if product_template[0].article_id:
            request.session['articleid'] = product_template[0].article_id
        else:
            request.session['articleid'] = 'xxxxxxxxxx'
        request.session['sapuomid'] = product_template[0].sap_uom_id 
        batchnos = self.get_product_batch()
        request.session['batchnos'] = batchnos
        if len(batchnos) > 0:
            request.session['is_batchnos'] = True
        else:
            request.session['is_batchnos'] = False
        return request.render('ranch_dc_project.warehouse_opname_trans_batch',datas)
    
    @http.route('/warehouse/opname/trans/batchother', type='http', auth='user', csrf=False)
    def trans_batch_other_find(self, redirect='/warehouse/opname/index', **post):
        datas = {}
        return request.render('ranch_dc_project.warehouse_opname_trans_batch_other',datas)

    @http.route('/warehouse/opname/trans/back', type='http', auth='user', csrf=False)
    def trans_back(self, redirect='/warehouse/opname/index'):
        datas = {}
        return request.render('ranch_dc_project.warehouse_opname_trans_product', datas)

    @http.route('/warehouse/opname/trans/qty', type='http', auth='user', methods=['GET','POST'], csrf=False)
    def trans_product(self, redirect='/warehouse/opname/index', **post):
        stock_inventory_trans_source_obj = http.request.env['stock.inventory.source']
        stock_inventory_trans_line_obj = http.request.env['stock.inventory.trans.line']
        datas = {}
        vals = {}
        if 'batchno' in post.keys():
            if not post['batchno']:
                datas.update({'msg': 'Batch cannot empty'})
                return request.render('ranch_dc_project.warehouse_opname_trans_batch', datas)
        try:
			batchno_temp = float(post['batchno'])
		except	valueError:
			datas.update({'msg': 'Batch Number Error'})
			datas.update({'trans_lines': []})
		return request.render('ranch_dc_project.warehouse_opname_trans_qty', datas)
		if len(post['batchno']) < 8:
			datas.update({'msg': 'Batch Number Error'})
			datas.update({'trans_lines': []})
		return request.render('ranch_dc_project.warehouse_opname_trans_qty', datas)
		
			request.session['batchno'] = post['batchno']
        else:
            datas.update({'msg': 'Batch cannot empty'})
            return request.render('ranch_dc_project.warehouse_opname_trans_batch', datas)

        stock_inventory_trans_line_args = [
            ('stock_inventory_trans_id','=', request.session.transid),
            ('product_id','=', request.session.productid),
            ('batchno','=', request.session.batchno)]
        
        #Check Trans Source
        args = [('stock_inventory_periode_id','=', request.session.periodeid),
                ('storagebin','=', request.session.gondolacode),
                ('article_id','=', request.session.articleid),
                ('batchno','=', request.session.batchno)
               ]
        stock_inventory_trans_source_ids = stock_inventory_trans_source_obj.search(args)
        if not stock_inventory_trans_source_ids:
            request.session['sourceid'] = False
        else:
            request.session['sourceid']  = stock_inventory_trans_source_ids[0].id    
    
        #Check Trans Line
        stock_inventory_trans_line_ids = stock_inventory_trans_line_obj.search(stock_inventory_trans_line_args) 
        if not stock_inventory_trans_line_ids:
            request.session['translineid'] = False                
        else:
            request.session['translineid'] = stock_inventory_trans_line_ids[0].id

        return request.render('ranch_dc_project.warehouse_opname_trans_qty', datas)
    
    @http.route('/warehouse/opname/trans/save', type='http', methods=['GET','POST'], auth='user', csrf=False)
    def trans_save(self, redirect='/warehouse/opname/index', **post):
        stock_inventory_obj = http.request.env['stock.inventory']
        stock_inventory = stock_inventory_obj.browse(request.session['periodeid'])
        stock_inventory_trans_line_obj = http.request.env['stock.inventory.trans.line']
        datas = {}
        _logger.info(post)
        allow_process = False
        try:
            qty = float(post['qty'])
        except ValueError:
            datas.update({'msg': 'Quantity Error'})
            datas.update({'trans_lines': []})
            return request.render('ranch_dc_project.warehouse_opname_trans_qty', datas)

        if qty >= 0 and qty < 1000000.0:
            if request.session['sapuomid'] != 'KG':
                if qty%1 == 0:
                    allow_process = True
            else:
                    allow_process = True
        if allow_process:
            vals = {}
            vals.update({'stock_inventory_trans_id': request.session['transid']})
            vals.update({'product_id': request.session['productid']})
            vals.update({'article_id': request.session['articleid']})
            vals.update({'batchno': request.session['batchno']})
            vals.update({'stock_inventory_trans_source_id': request.session['sourceid']})
            vals.update({'step': '1'})
            vals.update({'qty1': qty})
            vals.update({'qty2': qty})
            vals.update({'qty3': qty})
            if not request.session['translineid']:
                stock_inventory_trans_line_obj.create(vals)
                _logger.info("Create Trans Line")
            else:
                stock_inventory_trans_line_id  = stock_inventory_trans_line_obj.browse(request.session['translineid'])
                stock_inventory_trans_line_id.write(vals)
                _logger.info("Update Trans Line")

            args = [('stock_inventory_trans_id', '=', request.session.transid),
                    ('gondola_id', '=', request.session.gondolaid),
                    ('batchno','=', request.session.batchno)]
                    
            stock_inventory_trans_line_ids = stock_inventory_trans_line_obj.search(args, order='date desc')
            if len(stock_inventory_trans_line_ids) > 0:
                _logger.info('Find Last Product')
                stock_inventory_trans_line = stock_inventory_trans_line_ids[0]
                request.session['lastproduct'] = stock_inventory_trans_line.product_id.name
            else:
                _logger.info('Last Product not found')
                request.session['lastproduct'] = 'No Product'
            
            return request.render('ranch_dc_project.warehouse_opname_trans_product', datas)
        else:
            datas.update({'msg': 'Quantity Error'})
            datas.update({'trans_lines': []})
            return request.render('ranch_dc_project.warehouse_opname_trans_qty', datas)
        

    @http.route('/warehouse/opname/trans/close', type='http', auth='user', csrf=False)
    def trans_close(self, redirect='/warehouse/opname/index'):
        datas = {}
        return request.render('ranch_dc_project.warehouse_opname_gondola_find', datas)

