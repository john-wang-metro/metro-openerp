# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time
import datetime
from openerp import netsvc
from openerp.osv import fields,osv
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
from openerp.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT


class material_request(osv.osv):
    _name = "material.request"
    _inherit = "stock.picking"
    _table = "stock_picking"
    _description = "Material Request"

    _columns = {
        'type': fields.selection([('out', 'Sending Goods'), ('in', 'Getting Goods'), ('internal', 'Internal'), ('mr', 'Material Request'), ('mrr', 'Material Request Return')], 
                                 'Request Type', required=True, select=True, readonly=True, states={'creating':[('readonly',False)]}),
        'move_lines': fields.one2many('material.request.line', 'picking_id', 'Request Products', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}),
        'mr_dept_id': fields.many2one('hr.department', 'Department', states={'done':[('readonly', True)], 'cancel':[('readonly',True)]}),
        'create_uid': fields.many2one('res.users', 'Creator',readonly=True),
        
    }
    _defaults = {
        'type': 'mr',
        'state': 'creating',
    }

    def check_access_rights(self, cr, uid, operation, raise_exception=True):
        #override in order to redirect the check of acces rights on the stock.picking object
        return self.pool.get('stock.picking').check_access_rights(cr, uid, operation, raise_exception=raise_exception)

    def check_access_rule(self, cr, uid, ids, operation, context=None):
        #override in order to redirect the check of acces rules on the stock.picking object
        return self.pool.get('stock.picking').check_access_rule(cr, uid, ids, operation, context=context)

    def _workflow_trigger(self, cr, uid, ids, trigger, context=None):
        #override in order to trigger the workflow of stock.picking at the end of create, write and unlink operation
        #instead of it's own workflow (which is not existing)
        return self.pool.get('stock.picking')._workflow_trigger(cr, uid, ids, trigger, context=context)

    def _workflow_signal(self, cr, uid, ids, signal, context=None):
        #override in order to fire the workflow signal on given stock.picking workflow instance
        #instead of it's own workflow (which is not existing)
        return self.pool.get('stock.picking')._workflow_signal(cr, uid, ids, signal, context=context)
        
    def create(self, cr, uid, vals, context=None):
        vals['state'] = 'draft'
        if not vals.get('name') or vals.get('name','/')=='/':
            if vals['type'] == 'mrr':
                vals['name'] = self.pool.get('ir.sequence').get(cr, uid, 'material.request.return') or '/'
            else:
                vals['name'] = self.pool.get('ir.sequence').get(cr, uid, 'material.request') or '/'
                
        order =  super(material_request, self).create(cr, uid, vals, context=context)
        return order
#    def default_get(self, cr, uid, fields_list, context=None):
#        resu = super(material_request,self).default_get(cr, uid, fields_list, context)
#        return resu
    def search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False):
        #deal the 'date' datetime field query
        new_args = deal_args(self,args)
        return super(material_request,self).search(cr, user, new_args, offset, limit, order, context, count)    
             
#class material_return(osv.osv):
#    _name = "material.return"
#    _inherit = "material.request"
#    _description = "Material Return"
#    _defaults = {
#        'type': 'mrr',
#        'move_type': 'one',
#    }
#    def view_init(self, cr, uid, fields_list, context=None):
#        """Override this method to do specific things when a view on the object is opened."""
#        pass
#    def _get_default_form_view(self, cr, user, context=None):
#        resu = super(material_return,self)._get_default_form_view(cr,user, context)
#        return resu            
#    def fields_view_get(self, cr, user, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
#        resu = super(material_return,self).fields_view_get(cr, user, view_id, view_type, context, toolbar, submenu)
#        return resu            
        
class material_request_line(osv.osv):
    _name = "material.request.line"
    _inherit = "stock.move"
    _table = "stock_move"
    _description = "Material Request Line"
    _columns = {
        'picking_id': fields.many2one('material.request', 'MR#', select=True,states={'done': [('readonly', True)]}),
        'mr_emp_id': fields.many2one('hr.employee','Employee'),
        'mr_sale_prod_id': fields.char('Sale Product ID',size=8),
        'mr_notes': fields.text('Reason and use'),
        'mr_dept_id': fields.related('picking_id','mr_dept_id',string='Department',type='many2one',relation='hr.department',select=True),
        'mr_date_order': fields.related('picking_id','date',string='Order Date',type='datetime'),
        'pick_type': fields.related('picking_id','type',string='Picking Type',type='char'),
        'create_uid': fields.many2one('res.users', 'Creator',readonly=True),
    }
    def default_get(self, cr, uid, fields_list, context=None):
        resu = super(material_request_line,self).default_get(cr, uid, fields_list, context)
        #material_request.type: mr or mrr
        req_type = context.get('req_type')
        if not req_type:
            req_type = 'mr'
        loc_stock_id = None
        loc_prod_id = None
        #get the default stock location
        cr.execute('select c.id \n'+
                    'from res_users a  \n'+
                    'left join stock_warehouse b on a.company_id = b.company_id  \n'+
                    'left join stock_location c on b.lot_stock_id = c.id \n'
                    'where a.id = %s', (uid,))
        loc_src = cr.fetchone()
        if loc_src:
           loc_stock_id = loc_src[0]           
        #get the default production location
        loc_obj = self.pool.get('stock.location')
        prod_loc_ids = loc_obj.search(cr,uid,[('usage','=','production')],context=context)
        if prod_loc_ids and prod_loc_ids[0]:
            prod_loc = loc_obj.browse(cr,uid,prod_loc_ids[0],context=context)
            loc_prod_id = prod_loc.id
        #set the locations by the request type
        if req_type == 'mr':
           if loc_stock_id:
               resu.update({'location_id':loc_stock_id})
           if loc_prod_id:
               resu.update({'location_dest_id':loc_prod_id})
        if req_type == 'mrr':
           if loc_prod_id:
               resu.update({'location_id':loc_prod_id})
           if loc_stock_id:
               resu.update({'location_dest_id':loc_stock_id})                  
           
        return resu
    def onchange_product_id(self, cr, uid, ids, prod_id=False, loc_id=False,
                            loc_dest_id=False, ):
        """ On change of product id, if finds UoM, UoS, quantity and UoS quantity.
        @param prod_id: Changed Product id
        @param loc_id: Source location id
        @param loc_dest_id: Destination location id
        @param partner_id: Address id of partner
        @return: Dictionary of values
        """
        if not prod_id:
            return {}
        user = self.pool.get("res.users").browse(cr,uid,uid)
        ctx = {'lang': user.lang}

        product = self.pool.get('product.product').browse(cr, uid, [prod_id], context=ctx)[0]
        uos_id  = product.uos_id and product.uos_id.id or False
        result = {
            'product_uom': product.uom_id.id,
            'product_uos': uos_id,
            'product_qty': 1.00,
            'product_uos_qty' : self.pool.get('stock.move').onchange_quantity(cr, uid, ids, prod_id, 1.00, product.uom_id.id, uos_id)['value']['product_uos_qty'],
            'prodlot_id' : False,
        }
        if not ids:
            result['name'] = product.partner_ref
        if loc_id:
            result['location_id'] = loc_id
        if loc_dest_id:
            result['location_dest_id'] = loc_dest_id
        return {'value': result}
    def check_access_rights(self, cr, uid, operation, raise_exception=True):
        #override in order to redirect the check of acces rights on the stock.picking object
        return self.pool.get('stock.move').check_access_rights(cr, uid, operation, raise_exception=raise_exception)

    def check_access_rule(self, cr, uid, ids, operation, context=None):
        #override in order to redirect the check of acces rules on the stock.picking object
        return self.pool.get('stock.move').check_access_rule(cr, uid, ids, operation, context=context)

    def _workflow_trigger(self, cr, uid, ids, trigger, context=None):
        #override in order to trigger the workflow of stock.picking at the end of create, write and unlink operation
        #instead of it's own workflow (which is not existing)
        return self.pool.get('stock.move')._workflow_trigger(cr, uid, ids, trigger, context=context)

    def _workflow_signal(self, cr, uid, ids, signal, context=None):
        #override in order to fire the workflow signal on given stock.picking workflow instance
        #instead of it's own workflow (which is not existing)
        return self.pool.get('stock.move')._workflow_signal(cr, uid, ids, signal, context=context)    

    def search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False):
        #deal the 'date' datetime field query
        new_args = deal_args(self,args)
        return super(material_request_line,self).search(cr, user, new_args, offset, limit, order, context, count)   
        
class stock_move(osv.osv):
    _inherit = "stock.move" 
    _columns = {   
        'type': fields.related('picking_id', 'type', type='selection', selection=[('out', 'Sending Goods'), ('in', 'Getting Goods'), ('internal', 'Internal'), ('mr', 'Material Request'), ('mrr', 'Material Request Return')], string='Shipping Type'),
        'create_uid': fields.many2one('res.users', 'Creator',readonly=True),
    }

    def search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False):
        #deal the 'date' datetime field query
        new_args = deal_args(self,args)
        return super(stock_move,self).search(cr, user, new_args, offset, limit, order, context, count)  

 
class stock_picking(osv.osv):
    _inherit = "stock.picking" 
    _columns = {   
        'create_uid': fields.many2one('res.users', 'Creator',readonly=True),
    }  
    def search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False):
        #deal the 'date' datetime field query
        new_args = deal_args(self,args)
        return super(stock_picking,self).search(cr, user, new_args, offset, limit, order, context, count) 
class stock_picking_out(osv.osv):
    _inherit = "stock.picking.out"   
    def search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False):
        #deal the 'date' datetime field query
        new_args = deal_args(self,args)
        return super(stock_picking_out,self).search(cr, user, new_args, offset, limit, order, context, count)    
class stock_picking_in(osv.osv):
    _inherit = "stock.picking.in"   
    def search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False):
        #deal the 'date' datetime field query
        new_args = deal_args(self,args)
        return super(stock_picking_in,self).search(cr, user, new_args, offset, limit, order, context, count)     

class stock_inventory(osv.osv):
    _inherit = "stock.inventory"
    def unlink(self, cr, uid, ids, context=None):
        inventories = self.read(cr, uid, ids, ['state'], context=context)
        unlink_ids = []
        for s in inventories:
            if s['state'] in ['draft','cancel']:
                unlink_ids.append(s['id'])
            else:
                raise osv.except_osv(_('Invalid Action!'), _('Only the physical inventory orders with Draft or Cancelled state can be delete!'))

        return super(stock_inventory, self).unlink(cr, uid, unlink_ids, context=context)
    
class stock_inventory_line(osv.osv):
    _inherit = "stock.inventory.line"
    _columns = {   
        'image_medium': fields.related('product_id','image_medium',type='binary',String="Medium-sized image"),
        'state': fields.related('inventory_id','state',type='selection',selection=(('draft', 'Draft'), ('cancel','Cancelled'), ('confirm','Confirmed'), ('done', 'Done')),
                                string='Status',readonly=True),
    }
#stock physical inventroy move
#class stock_inventory_move(osv.osv):
#    _name = "stock.inventory.move"
##    _table = "stock_inventory_move_rel"
#    _table = "stock_move"
#    _columns = {   
#        'inventory_id': fields.many2one('stock.inventory','Inventory Referance'),
#        'inventory_state': fields.related('inventory_id','Inventory State',type='selection',selection=(('draft', 'Draft'), ('cancel','Cancelled'), ('confirm','Confirmed'), ('done', 'Done')),
#                                string='Status',readonly=True),
#        'move_id': fields.many2one('stock.move','Inventory Referance'),
#        'product_id': fields.related('move_id','product_id',type='many2one',relation="product.product",String="Product",readonly=True,),
#        'product_qty': fields.related('move_id','product_qty',type='float',String="Quantity",readonly=True,),
#        'location_id': fields.related('move_id','location_id',type='many2one',relation="stock.location",String="Source Location",readonly=True,),
#        'location_dest_id': fields.related('move_id','location_dest_id',type='many2one',relation="stock.location",String="Destination Location",readonly=True,),
#        'state': fields.related('move_id','state',type='selection',selection=[('draft', 'New'),
#                                   ('cancel', 'Cancelled'),
#                                   ('waiting', 'Waiting Another Move'),
#                                   ('confirmed', 'Waiting Availability'),
#                                   ('assigned', 'Available'),
#                                   ('done', 'Done'),
#                                   ],String="Destination Location",readonly=True,),
#    }
           
def deal_args(obj,args):  
    new_args = []
    for arg in args:
        fld_name = arg[0]
        if fld_name == 'date':
            fld_operator = arg[1]
            fld_val = arg[2]
            fld = obj._columns.get(fld_name)
            #['date','=','2013-12-12 16:00:00'] the '16' was generated for the timezone
            if fld._type == 'datetime' and fld_operator == "=" and fld_val.endswith('00:00'):
                time_start = [fld_name,'>=',fld_val]
                time_obj = datetime.datetime.strptime(fld_val,DEFAULT_SERVER_DATETIME_FORMAT)
                time_obj += relativedelta(days=1)
                time_end = [fld_name,'<=',time_obj.strftime(DEFAULT_SERVER_DATETIME_FORMAT)]
                new_args.append(time_start)
                new_args.append(time_end)
            else:
                new_args.append(arg)
        else:
            new_args.append(arg)    
    return new_args