create table stackexchange_db.update_statuses
(
    id integer primary key,
    v_name varchar(255)
);
alter table stackexchange_db.update_statuses owner to stackexchange_bot;
insert into stackexchange_db.update_statuses (id, v_name) values (1, 'Done');
insert into stackexchange_db.update_statuses (id, v_name) values (2, 'Processing');