# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
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

from openerp.osv import fields, osv
from openerp.tools.translate import _

import base64
import xlrd
import re
import types
import os

class bom_import(osv.osv_memory):
    _name = "bom.import"
    _description = "Import Bill of Material"

    _columns = {
        'mrp_bom_id': fields.many2one('mrp.bom','BOM'),
        'import_file': fields.binary('Select your Excel File', filters="*.xls", required=True),
        'file_template': fields.binary('Template File', readonly=True),
        'file_template_name': fields.char('Template File Name'),
    }
    def _get_template(self, cr, uid, context):
        cur_path = os.path.split(os.path.realpath(__file__))[0]
        path = os.path.join(cur_path,'bom_import_template.xls')
        data = open(path,'rb').read().encode('base64')
        return data
            
    _defaults = { 
        'file_template': _get_template,
        'file_template_name': 'bom_import_template.xls'
    }    
    def default_get(self, cr, uid, fields, context=None):
        """
         To get default values for the object.
         @param self: The object pointer.
         @param cr: A database cursor
         @param uid: ID of the user currently logged in
         @param fields: List of fields for which we want default values
         @param context: A standard dictionary
         @return: A dictionary with default values for all field in ``fields``
        """
        if context is None:
            context = {}
        res = super(bom_import, self).default_get(cr, uid, fields, context=context)
        mrp_bom_id = context and context.get('active_id', False) or False
        if mrp_bom_id:
            mrp_bom = self.pool.get('mrp.bom').browse(cr, uid, mrp_bom_id, context=context)
            res.update({'mrp_bom_id': mrp_bom_id, 'product_id':mrp_bom.product_id.id, 'name':mrp_bom.name})
        return res

    def import_data(self, cr, uid, ids, context=None):
        """ To Import BOM according to the excel file
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: the ID or list of IDs if we want more than one
        @param context: A standard dictionary
        @return:
        """
        if context is None:
            context = {}
        
        order = self.browse(cr,uid,ids[0],context=context)
        #get the uploaded data
        import_data = base64.decodestring(order.import_file)
        excel_data = xlrd.open_workbook(file_contents=import_data,formatting_info=True)
        sheet = excel_data.sheets()[0]
        row_cnt = sheet.nrows
        
        '''
        level_no: the root product will be ‘root’, other follows the #.#.# format, and must be unique in one excel.
        erp_part_no: the part# of erp
        quantity:the quantity
        '''
        #1 check the column list: 'level_no,part_no,bom_name,quantity' must be in the list
        row_data = sheet.row_values(0);
        level_no_idx = 0
        part_no_idx = 0
        bom_name_idx = 0
        quantity_idx = 0
        id_idx = -1
        try:
            # get the data column index
            level_no_idx = row_data.index('level_no')
            part_no_idx = row_data.index('part_no')
            bom_name_idx = row_data.index('bom_name')
            quantity_idx = row_data.index('quantity')
        except Exception:
            raise osv.except_osv(_('Error!'), _('please make sure the "level_no, part_no, bom_name, quantity" columns in the column list.'))
        try:
            # get the 'id' column index
            id_idx = row_data.index('id')
        except Exception:
            id_idx = -1 
        #2 loop to check data, and put data to cache if all are OK
        '''
        the regex for the level# like: 1, 1.1, 1.1.1
        ([1-9]+\d*\.)* : no, one or more char like "#.", and the "#" must be greater than zero
        [1-9]+\d*$ : the suffix must be a number, and greater than zero 
        '''
        level_pattern = re.compile(r'L([1-9]+\d*\.)*[1-9]+\d*$')
        root_level_no = 'root'
        parsed_rows = {}
        prod_obj = self.pool.get('product.product')
        for i in range(1,row_cnt):
            row_data = sheet.row_values(i);
            #=========validate the level_no============
            level_no = row_data[level_no_idx]
            parsed_row = {}
            if level_no != root_level_no:   
                if level_no is not types.StringType:
                    level_no = str(level_no)
                    if level_no == '':
                        level_no = '0'
                #check the level_no format
                if not level_pattern.match(level_no):
                    raise osv.except_osv(_('Error!'), _('level_no %s at row %s must follow the format #.#.#'%(level_no, i+1,)))
                #level_no must be unique
                if level_no in parsed_rows:                    
                    raise osv.except_osv(_('Error!'), _('level_no %s at row %s already exists, duplicated with order rows!'%(level_no, i+1,)))
                #find the parent row, level_no must have parent
                parent_level_no = ''
                pos = level_no.rfind('.')
                if pos != -1:
                    parent_level_no = level_no[0:pos]
                    if parent_level_no not in parsed_rows:
                        raise osv.except_osv(_('Error!'), _('level_no %s at row %s can not find the parent BOM'%(level_no, i+1,)))
                else:
                    parent_level_no = 'root'
                #add to parent row's childs
                parent_level_row = parsed_rows.get(parent_level_no)
                childs = parent_level_row.get('bom_lines')
                if not childs:
                    childs = []
                    parent_level_row.update({'bom_lines':childs})
                childs.append((0, 0, parsed_row))
            #=========check the product existing============
            product = None
            if id_idx < 0 or not row_data[id_idx] or row_data[id_idx] == '':
                #if there is no id data, then use default_code to get product id
                ids = prod_obj.search(cr,uid,[('default_code','=',row_data[part_no_idx])],context=context)
                if not ids or len(ids) == 0:
                    raise osv.except_osv(_('Error!'), _('the product of row %s does not exist'%(i+1,)))
                product = prod_obj.browse(cr, uid, ids[0], context=context)
            else:
                product = prod_obj.browse(cr, uid, row_data[id_idx], context=context)
                if not product:
                    raise osv.except_osv(_('Error!'), _('the product of row %s does not exist'%(i+1,)))
                    
                
            #=========check the quantity============
            quantity = row_data[quantity_idx]
            pattern_number = re.compile(r'\d+\.*\d*$')
            if quantity is not types.StringType:
                quantity = str(quantity)
                if quantity == '':
                    quantity = '0'
            print float(quantity)
            if not pattern_number.match(quantity) or float(quantity) == 0:
                raise osv.except_osv(_('Error!'), _('the quantity of row %s must be a number and larger than zero!'%(i+1,)))
            
            #=========set the row data============
            bom_name = row_data[bom_name_idx]
            if not bom_name or bom_name == '':
                bom_name = product.name
            parsed_row.update({'product_id':product.id,
                             'product_uom':product.uom_id.id,
                            'name':bom_name,
                            'code':level_no,
                            'product_qty':quantity,})
            parsed_rows.update({level_no:parsed_row})
        
        #having mrp_bom_id: do top BOM updating
        mrp_bom_obj = self.pool.get('mrp.bom')
        bom_master = parsed_rows['root']
        if order.mrp_bom_id:
            #if from an existing bom ID, then close the window, and refresh parent to show the new data
            mrp_bom_obj.update(cr, uid, order.mrp_bom_id, {'bom_ids':bom_master['bom_ids']}, context=context)            
            return {'type': 'ir.actions.act_window_close'}  
        else:
            #Show the created new BOM in list view
            new_bom_id = mrp_bom_obj.create(cr, uid, bom_master, context=context)
            return {
                'domain': "[('id', '=', %s)]"%(new_bom_id,),
                'name': _('MRP BOM'),
                'view_type':'form',
                'view_mode':'tree,form',
                'res_model': 'mrp.bom',
                'type':'ir.actions.act_window',
                'context':context,
            }   

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: