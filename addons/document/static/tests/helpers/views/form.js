export const basicDocumentsOperationFormArch = `
<form>
    <field name="display_name" invisible="1" force_save="1"/>
    <field name="user_permission" invisible="1" force_save="1"/>
    <field name="document_ids" invisible="1"><list><field name="display_name"/></list></field>
    <field name="operation" readonly="1" invisible="1"/>
    <field name="attachment_id" invisible="1" force_save="1"/>
    <sheet>
        <field
            name="destination"
            widget="documents_user_folder_id_char"
            options="{
                'extraUpdateFields': ['display_name', 'user_permission'],
                'ulClass': 'o_documents_operation_search_panel',
            }"
        />
    </sheet>
    <footer>
        <widget name="documents_operation_confirmation"/>
        <widget name="documents_operation_new_folder"/>
        <button string="Discard" special="cancel" class="btn-secondary"/>
    </footer>
</form>`;
